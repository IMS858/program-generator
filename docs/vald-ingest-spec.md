# VALD DynaMo ingest · spec for the Coach OS thread

Paste-ready. This describes work that belongs in Coach OS (Next.js + Supabase),
not in the program generator.

**Division of labour, and why:**

| Concern | Where | Because |
|---|---|---|
| OAuth, credentials, region URL | Coach OS | needs a secrets store |
| Incremental sync cursor | Coach OS | needs persistent state |
| VALD athlete → IMS client identity | Coach OS | needs the client table |
| Storing measurements | Coach OS | needs the database |
| **Test vocabulary + payload shape** | **Generator** | a mapping table in two places drifts |
| Routing, load, volume decisions | Generator | already built and tested |

The generator exposes `POST /api/vald/transform` so Coach OS never has to
reimplement the mapping. Post it raw VALD test objects, get back a validated
`objective_measures` block ready for `POST /api/generate`.

---

## Step 0 · get API access (do this during the DynaMo negotiation)

This is a contract step, not a technical one, and it has a lead time.

1. Get your organization ID from VALD Hub.
2. Email `support@vald.com` requesting external API access, include the org ID.
3. **They will require you to sign an API License Agreement** before issuing
   anything.
4. Once approved they send a `clientId` and `clientSecret`. **The link expires
   in seven days** — have somewhere to put them before you ask.

Get this into the DynaMo deal alongside the flat 3-year pricing and the Hub
seats. It is much cheaper as a line in the original agreement than as a
separate negotiation in November.

Also note: VALD migrated external API authentication to a new provider in
March 2026. Any sample code or blog post older than that is stale — including
the `valdr` R package, which needed refreshed credentials.

---

## Step 1 · configuration

```
VALD_CLIENT_ID
VALD_CLIENT_SECRET
VALD_TENANT_ID          # from the External Tenants API
VALD_DYNAMO_BASE_URL    # US East: https://prd-use-api-extdynamo.valdperformance.com/
```

The base URL is region-specific. IMS is San Diego, so US East — confirm with
VALD support if the tenant was provisioned elsewhere.

Cache the access token. Do not fetch one per request.

---

## Step 2 · identity mapping · the piece that will actually bite

Every test carries an `athleteId`. Nothing in it knows about IMS client ids.

```sql
alter table clients add column vald_athlete_id uuid unique;
```

Two ways to populate it, and the second is better:

1. **Manual link.** A dropdown on the client profile: "link to VALD athlete."
   Fine for a roster this size. Do this first.
2. **Push profiles to VALD.** The External Profiles API accepts writes, so
   Coach OS can create the VALD profile when a client is created and own the
   identity from the start. This is the right end state — it makes Coach OS the
   source of truth and removes the possibility of a mismatched link.

**A test whose `athleteId` has no linked client must go to a review queue, not
get dropped and not get guessed.** Attaching a measurement to the wrong person
is the worst failure mode in this whole system: it silently changes someone's
prescription.

---

## Step 3 · the sync

Two endpoints, in order.

**List tests** — `GET /v2022q2/teams/{tenantId}/tests`

Required query params: `modifiedFromUtc`, `testFromUtc`, `testToUtc`. Optional:
`athleteId`, `page`, `includeRepSummaries`, `includeReps`.

- Returns **50 records per page**; increment `page` until you pass `totalPages`.
- `testFromUtc` is inclusive, `testToUtc` is exclusive.
- **Persist `modifiedFromUtc` after each successful full fetch.** That cursor is
  the whole reason this belongs in Coach OS. Store it per tenant:

```sql
create table vald_sync_state (
  tenant_id          uuid primary key,
  modified_from_utc  timestamptz not null,
  last_run_at        timestamptz,
  last_error         text
);
```

**Get test detail** — `GET /v2022q2/teams/{tenantId}/tests/{testId}`

This is where the numbers are. Cache by `testId`; tests are immutable once
analysed.

Run the sync on a cron (hourly is generous) plus a manual "sync now" button on
the client profile, because the coach will want the numbers before the client
has left the building.

---

## Step 4 · what the payload actually looks like

Corrections to assumptions worth stating, because two of them changed the plan:

**ROM comes back in degrees.** `maxRangeOfMotionDegrees` sits in
`repetitionTypeSummaries` at the test level. Quaternions are only in the raw
`/trace` endpoint. **ROM auto-imports** — it does not have to stay manual, which
is what I assumed before reading the schema.

**RFD is free.** `maxRateOfForceDevelopmentNewtonsPerSecond` is on the same
summary object. The original plan had rate of force development gated behind a
later trace-parsing phase. It is not — it arrives with every strength test from
day one. RFD is more sensitive to detraining and declines earlier with age than
peak force does, so this is a real gain for no work.

**Sides arrive pre-split.** For a `LeftThenRight` test there is always a
`repetitionTypeSummaries` entry for `LeftSide` and one for `RightSide`. VALD's
guidance is to use `repetitionTypeSummaries` rather than the raw `repetitions`
array.

**Force is in Newtons.** The generator accepts `"unit": "N"` and converts.

**ROM can be negative.** VALD's own example is −32° (a knee extension deficit).
Anything validating degrees must allow it — the first cut of our validator
stopped at −30 and would have rejected real data.

**Test identity is `bodyRegion` + `movement`.** VALD explicitly warns against
using `laterality` or attachments to build a test name, because it breaks
aggregation across similar tests.

**Asymmetry is precomputed** in the `asymmetries` array as a percentage. We
compute our own from both sides anyway — worth cross-checking the two during
the dry run rather than trusting either blindly.

---

## Step 5 · transform and generate

```ts
// 1 · hand the raw tests to the generator's transform endpoint
const t = await fetch(`${GENERATOR_URL}/api/vald/transform`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    current: currentTests,        // raw VALD test detail objects
    previous: previousTests,      // optional
    bodyweight_lb: client.bodyweight_lb,
  }),
}).then(r => r.json());

// 2 · anything unmapped is a vocabulary gap, not a failure
if (t.unmapped.length) {
  logForReview(t.unmapped);       // e.g. [{bodyRegion:'Thumb', movement:'Opposition'}]
}

// 3 · store, then generate
await saveMeasurements(clientId, t.objective_measures);

const pdf = await fetch(`${GENERATOR_URL}/api/generate`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ ...assessmentPayload,
                         objective_measures: t.objective_measures }),
});
```

**Unmapped tests are skipped with a warning, never fatal.** One novel movement
type must not fail an entire assessment sync. `/api/generate` rejects an unknown
test id with a 400 — correct for a hand-typed payload, wrong for a batch — so
the transform endpoint absorbs that and reports it instead.

Run `unmapped_tests()` over a month of real data before trusting the sync. It
tells you exactly what the studio measures that the table does not know about
yet, and adding a row to `VALD_TEST_MAP` is a one-line change.

---

## Step 6 · provenance in the UI

Every measurement carries `source: "manual" | "vald_api"` and a `source_id`
(the VALD `testId`). The coach page already prints this and tags rows when an
assessment mixes both.

Carry it into the profile UI too. Hand-typed and synced numbers fail in
different ways — a typed number can be a transcription error, a synced one can
be attached to the wrong athlete — and the coach should be able to tell at a
glance which kind of wrong they might be looking at.

---

## Sequencing against the two weeks

| When | What |
|---|---|
| **Now** | Request API access. It gates everything and it needs a signature. |
| Before hardware | Manual capture path (already built and working). Ship this regardless. |
| Week 1 with hardware | `vald_athlete_id` column + manual link UI. Nothing else. |
| Week 2–3 | Sync job, cursor table, review queue for unlinked athletes. |
| Week 4+ | Push profiles to VALD so Coach OS owns identity. Surface RFD. |

**Do not let the API work delay capture.** Manual entry of ten numbers takes
under a minute and is not the bottleneck. Measurements you never took are
unrecoverable; an integration that lands three weeks late costs nothing but
typing.
