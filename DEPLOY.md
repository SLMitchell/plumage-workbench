# Deploying as a new service in the existing birdlogger Railway project

A Railway **project** can hold multiple **services**. This adds the Plumage Workbench as a
second service alongside `birdnews`, sharing the same project but building and running
independently, with its own URL. Your production `birdnews` app is not touched.

## 0. Prerequisites — push this repo to GitHub

From `OneDrive/Documents/plumage-workbench`:

```bash
git branch -M main
git remote add origin https://github.com/SLMitchell/plumage-workbench.git   # create the empty repo first on github.com
git push -u origin main
```

## 1. Add the service to the birdlogger project

1. Open [railway.app](https://railway.app) → open the **project** that runs `birdnews`.
2. Click **Create** (or **+ New**) on the project canvas → **GitHub Repo**.
3. Pick **`plumage-workbench`**. Railway creates a new service and starts a build.
   - Nixpacks auto-detects Python from `requirements.txt`.
   - `railway.toml` supplies the start command and the `/healthz` health check.

## 2. Set the service variables

Open the new service → **Variables** → add:

| Variable | Value |
|----------|-------|
| `WORKBENCH_PASSWORD` | your chosen shared password (**required** — without it the app runs open) |
| `SECRET_KEY` | a long random hex: `python -c "import secrets; print(secrets.token_hex(32))"` |

Leave `ML_SSL_VERIFY` unset (defaults to on — correct on Railway). `EBIRD_API_KEY` is
optional (defaults to eBird's public web key).

Saving variables triggers a redeploy.

## 3. Give it a public URL

Service → **Settings → Networking → Public Networking → Generate Domain**.
Railway auto-targets the app's `$PORT`. You get `https://<something>.up.railway.app`.

## 4. Verify

- `https://<url>/healthz` → `ok`
- `https://<url>/` → password page → enter `WORKBENCH_PASSWORD` → the workbench loads.
- Pull a small two-species set to confirm images and search work.

## 5. Link it from the birdnews dashboard

Add an anchor wherever your nav is rendered in `birdnews/app.py`:

```html
<a href="https://<url>" target="_blank" rel="noopener">🪶 Plumage Workbench</a>
```

---

## Alternatives

- **Keep one GitHub repo (monorepo):** put these files in a subfolder of the `birdnews`
  repo instead, and in step 1 set the new service's **Settings → Source → Root Directory**
  to that subfolder. Everything else is identical. (Trade-off: not a clean standalone
  open-source repo.)
- **Same domain, under a path** (e.g. `birdnews.com/plumage`) instead of a subdomain: that
  requires mounting this app *inside* the birdnews process with
  `werkzeug.middleware.dispatcher.DispatcherMiddleware`, rather than a separate service.
  More coupling; only worth it if a subdomain link is unacceptable.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Build fails, no Python detected | ensure `requirements.txt` is at the service's root directory |
| App boots but 502 | it must bind `$PORT`; the provided `railway.toml`/`Procfile` already do |
| Health check failing | path is `/healthz`; it's open (no auth) by design |
| eBird/ML calls fail with TLS error | only happens on some local machines; on Railway leave `ML_SSL_VERIFY` at default |
| Page loads with no password prompt | `WORKBENCH_PASSWORD` isn't set on the service |
