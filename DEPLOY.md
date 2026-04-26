# Deploy to Vercel

Get your assessment form live at a public URL. Takes about 5 minutes.

## How it's wired

```
Client fills form in browser
  → browser POSTs JSON to /api/generate
  → Flask app on Vercel generates the PDF
  → browser downloads it automatically
```

Everything runs from a single Flask app at `api/index.py`. Vercel auto-detects it from `requirements.txt`.

---

## Step 1 · Push this repo to GitHub

```bash
cd ims-method-vercel
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/ims-method.git
git push -u origin main
```

---

## Step 2 · Connect to Vercel

1. Go to [vercel.com](https://vercel.com) → sign in with GitHub
2. **Add New…** → **Project**
3. Select your repo → **Import**
4. **Framework Preset** should auto-detect as **Flask** (Vercel sees `flask` in requirements.txt and `api/index.py` with `app = Flask(__name__)`)
5. Leave everything else as default
6. Click **Deploy**

Wait ~2 minutes for the first build.

---

## Step 3 · Your site is live

You'll get a URL like ·

```
https://ims-method.vercel.app
```

Open it · form loads. Fill it out, hit Generate PDF Plan, PDF downloads.

---

## Updating

Just push to GitHub ·

```bash
git add .
git commit -m "Whatever changed"
git push
```

Vercel auto-redeploys in ~1 minute.

---

## Custom domain (optional)

If you own `imsmethod.com` and want the form at `assess.imsmethod.com` ·

1. Vercel project → **Settings** → **Domains**
2. Add `assess.imsmethod.com`
3. Vercel shows you a CNAME record to add at your registrar
4. Add it at your DNS provider (GoDaddy, Cloudflare, etc.)
5. Wait ~5 min for DNS

Done.

---

## Local development

Want to test changes before deploying ·

```bash
pip install -r requirements.txt
python3 api/index.py
```

Open `http://localhost:3000/`. Both the form AND the PDF generation work locally.

---

## Troubleshooting

**"No python entrypoint found" on deploy ·**
You're on an older version of this repo. Re-download the zip — the current version has `api/index.py` with a Flask `app` variable, which Vercel auto-detects.

**500 error when hitting Generate ·**
Vercel project → **Functions** → click `api/index.py` → see the error trace. Usually it's a missing dependency (make sure `flask`, `reportlab`, `Pillow` are in `requirements.txt`) or a font issue (the code falls back to Times/Helvetica automatically if Lora/Poppins aren't available — shouldn't crash).

**Cold start feels slow first time ·**
Free tier sleeps after inactivity · first request after a gap wakes it up (~1-2 sec). Subsequent requests are instant.

---

## Limits on Vercel free tier

- Function runs up to 30 sec (we use ~4 sec, plenty of headroom)
- 100 GB bandwidth/month (each PDF ~100 KB = room for ~1M plans)
- Unlimited invocations
- No cost until you pass the free tier

You won't hit the limits.
