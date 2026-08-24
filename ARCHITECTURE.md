# Architecture & relationship to the birdlogger dashboard

This documents what the Plumage Workbench is, how it is built, and — the point most
worth being explicit about — **how it is deliberately separated from the birdlogger
dashboard (`birdnews`)**. Read this before wiring the two together more tightly.

## What this is

A self-contained tool for **comparative plumage morphometrics**: pull photo sets for any
two eBird taxa from the Macaulay Library, define your own regions and colour/texture
measurements on any part of the bird, annotate the images, and get an in-browser PCA plus a
geographic map of the variation. It is a single Flask app that serves one HTML page and
proxies a few upstream requests. All the analysis (white-balance, CIELAB, region stats,
PCA, stats) runs **client-side in the browser**.

## The division from `birdnews` (the birdlogger dashboard)

The workbench is a **separate GitHub repo and a separate Railway service**. It is *linked
from* the dashboard by a plain hyperlink and shares nothing else with it.

| | birdlogger dashboard (`birdnews`) | Plumage Workbench (this repo) |
|---|---|---|
| GitHub repo | `SLMitchell/birdnews` | `SLMitchell/plumage-workbench` |
| Railway | its own service | its own service (may sit in the same project) |
| Framework | Flask (large `app.py`, ~360 KB, 50+ routes) | Flask (one small `app.py`) |
| Auth | Flask-Login, per-user, Postgres-backed | one shared password (`WORKBENCH_PASSWORD`), no users |
| Database | Postgres (sightings, users, gazetteer, eBird links) | **none** |
| Persistence | server-side DB | browser `localStorage` + JSON export/import |
| Shared code | — | **none** |
| Connection between them | **a nav link only** | — |

**Why separate, not embedded:**
1. **Isolation of production.** The dashboard is a large, live app with real user data. The
   workbench never imports its code, touches its database, or shares its process, so it
   cannot break it.
2. **Open source.** The workbench is MIT-licensed and meant to be public; keeping it in its
   own repo with no dashboard code or secrets makes that clean.
3. **Different security model.** The dashboard gates everything behind per-user login; the
   workbench only needs a light shared-password gate, so coupling their auth would be
   friction with no benefit.
4. **Independent deploys.** Each redeploys on its own push without rebuilding the other.

**The only integration point** is a link in the dashboard nav, e.g.
`<a href="https://<workbench-url>" target="_blank" rel="noopener">Plumage Workbench</a>`.
If closer integration is ever wanted (same domain under a path), the intended route is a
Werkzeug `DispatcherMiddleware` mount — **not** merging the code into `birdnews/app.py`.

## Why there is a backend at all

Macaulay's image CDN (`cdn.download.ams.birds.cornell.edu`) sends **no CORS headers**. A
browser can display those images, but the moment one is drawn to a `<canvas>` the canvas is
"tainted" and `getImageData()` is refused — which would make in-browser colour analysis
impossible. Serving the page **and** proxying the images from the **same origin** removes
the taint. That is the whole reason a static page won't do and a tiny server is required.
The backend also solves the Macaulay search API's Anubis proof-of-work challenge and looks
up eBird taxon codes, so the browser never has to.

## Components

```
app.py          Flask: password gate + proxy routes + serves the page
ml_client.py    Macaulay client that solves the Anubis proof-of-work challenge
workbench.html  the entire frontend (single file: UI + all analysis)
requirements.txt / Procfile / railway.toml / .python-version   deploy config
```

### Backend routes (`app.py`)
- `GET /` → serves `workbench.html` (password-gated)
- `GET /login`, `/logout` → shared-password session gate
- `GET /healthz` → open; Railway health check + the app's own light "is the backend up?" ping
- `GET /api/taxon?q=` → eBird taxon autocomplete → `[{code,name,sci}]`
- `GET /api/search?taxon=&age=&count=&sort=` → Macaulay media search (paginated, Anubis solved)
- `GET /api/status` → probes eBird / Macaulay search / image CDN (cached 60 s) for the UI's
  "Test connection" button
- `GET /img/<assetId>/<size>` → proxies the Cornell CDN image **same-origin** (in-memory cache)

The Anubis session is **warmed in a background thread at boot** and **re-solved automatically**
on expiry (the cause of the old "worked then suddenly stopped" symptom).

### Frontend (`workbench.html`)
Five tabs — Query, Features, Annotate, Analyse, Map — plus a connection-warning banner.
Everything numeric is a faithful in-JS port of the original Python pipeline
(grey-world white balance → sRGB→CIELAB → region stats → chevron texture → PCA via a Jacobi
eigensolver); the port was validated against numpy. Notable behaviours:
- **Custom regions + measurements**, with optional region-vs-region contrasts.
- **Per-region "exclude dark" cutoff** (e.g. drop a black pupil so only iris colour is
  measured), calibrated live in the annotator with the excluded pixels shown in red.
- **Annotation**: brush painting; scroll = brush size, Ctrl+scroll/±/0 = zoom, H/Alt/middle-drag = pan.
- **Analyse**: PCA scatter (species = between, individual = within), Cohen's d / AUC /
  silhouette, ICC repeatability, per-photo ↔ per-individual aggregation.
- **Map**: Leaflet + OpenStreetMap tiles; points coloured by species, or by PC1/PC2/any
  feature on a white→red scale with the species shown on the marker ring.

### State & data
No server-side storage. Session state (species, feature set, pulled list, strokes) lives in
`localStorage` and round-trips through **Export / Import annotations JSON** for resuming work.
The only outbound data is the anonymous read-only queries to eBird and Macaulay.

## Configuration (environment variables)
| Variable | Purpose |
|----------|---------|
| `WORKBENCH_PASSWORD` | shared password gating the page (**required in production**) |
| `SECRET_KEY` | Flask session signing key (random per-boot if unset) |
| `EBIRD_API_KEY` | eBird taxon lookup key (defaults to eBird's public web key) |
| `ML_SSL_VERIFY` | `0` to disable TLS verification (only needed on some local Pythons) |
| `IMG_CACHE_MAX` | max images held in the in-memory cache (default 800) |

## Deploy
Railway + Nixpacks (`railway.toml`), gunicorn, health check `/healthz`. See `DEPLOY.md` for
adding it as a service in the birdlogger Railway project. Every push to `main` redeploys.

## External dependencies
- **Macaulay Library / Cornell Lab** — photos and search (respect their terms; the app
  throttles and caches).
- **eBird** — taxon-code lookup.
- **Leaflet + OpenStreetMap** — map tiles (loaded from CDN; fine because this is a real
  deployed origin, not a sandboxed artifact).

## Boundaries to preserve
- Do not import `birdnews` code or its database here, and do not add workbench routes to
  `birdnews/app.py`. Keep the link as the only join.
- Keep secrets out of the repo (`.env` is git-ignored; `.env.example` documents the vars).
- Any new upstream calls go through the backend proxy pattern so the page stays same-origin.
