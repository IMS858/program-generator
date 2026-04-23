# Deploy to Vercel

One-time setup. After this, every time you push to GitHub, the site updates automatically.

## What you're deploying

- `web/index.html` → the form at `yourname.vercel.app/`
- `api/generate.py` → the PDF generator at `yourname.vercel.app/api/generate`

When someone fills the form and hits **Generate PDF Plan**, the browser POSTs to `/api/generate`, the server builds the program + renders the PDF, and the browser downloads it automatically.

---

## Step 1 · Push this repo to GitHub

If you haven't already ·

```bash
cd ims-method
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/ims-method.git
git push -u origin main
```

Or if you already have it on GitHub, just make sure `api/generate.py` and `vercel.json` are committed.

---

## Step 2 · Connect GitHub to Vercel

1. Go to [vercel.com](https://vercel.com) → sign in with GitHub
2. Click **Add New…** → **Project**
3. Select your `ims-method` repo → **Import**
4. Framework preset · leave as **Other**
5. Don't change any other settings — `vercel.json` handles the config
6. Click **Deploy**

Wait ~2 minutes for the first build.

---

## Step 3 · Your site is live

When it's done, Vercel gives you a URL like ·

```
https://ims-method.vercel.app
```

Open it · the assessment form loads. Fill it out, hit Generate PDF Plan, the PDF downloads.

---

## Step 4 (optional) · Custom domain

If you own `imsmethod.com` and want the form at `imsmethod.com/assessment` ·

1. Vercel project → **Settings** → **Domains**
2. Add `imsmethod.com` or a subdomain like `assess.imsmethod.com`
3. Vercel shows you DNS records to add at your registrar (GoDaddy/Cloudflare/whoever)
4. Add the records, wait ~5 min, done

For a subpath like `imsmethod.com/assessment`, you'd need to configure the root domain to proxy that path to Vercel · more complex. Easiest path is `assess.imsmethod.com`.

---

## Updating the form or generator

Just push to GitHub ·

```bash
git add .
git commit -m "Update the thing"
git push
```

Vercel detects the push and redeploys in ~1 minute. No manual redeploy needed.

---

## Limits on Vercel free tier

- Function runs up to 30 sec (we use ~4 sec, plenty of headroom)
- 100 GB bandwidth/month (huge — each PDF is ~100 KB, so that's ~1M plans)
- Unlimited requests
- Sleeps after inactivity but wakes in ~1 sec

You won't hit the limits.

---

## If something breaks

**Form loads but Generate fails with an error ·** Vercel logs will tell you why. Go to Vercel project → **Functions** → click the function → see the error trace.

**Form doesn't load at all ·** Check `vercel.json` is in the repo root. Check the Vercel build log for errors.

**PDF download works but looks wrong ·** Check the browser console for JS errors. Font issues usually mean Lora/Poppins aren't found — the code falls back to Times/Helvetica automatically but it'll look less polished.

---

## Testing it locally before deploying

```bash
pip install -r requirements.txt
pip install vercel-python  # optional
```

You can't easily simulate Vercel's routing locally, but you can verify the server function works ·

```bash
python3 -c "
import sys, json
sys.path.insert(0, 'api')
from generate import build_program_pdf

with open('examples/sarah_input.json') as f:
    form = json.load(f)
pdf_bytes, name = build_program_pdf(form)
with open('test.pdf', 'wb') as f:
    f.write(pdf_bytes)
print(f'✓ Generated {len(pdf_bytes):,} bytes for {name}')
"
```
