# 🪶 Plumage Workbench

A browser-based tool for **comparative plumage morphometrics**. Pull photo sets for
any two [eBird](https://ebird.org) taxa straight from the [Macaulay Library](https://www.macaulaylibrary.org),
define your **own** regions and colour/texture measurements on any part of the bird,
annotate the images, and get a live **PCA** plus a **geographic map** of the variation —
all without downloading a single image by hand.

Built to test questions like *"do these two similar taxa separate when their plumage is
measured numerically?"* and *"is a feature a stable trait of the individual, or just
photo-to-photo noise?"*, and to see how features vary across a species' range.

---

## What it does

1. **Query** — type any two species (eBird autocomplete), choose age/count/sort, and pick
   which metadata to carry through. Images are pulled live from the Macaulay Library.
2. **Features** — define your own named regions (paintable layers on any body part) and
   choose the measurements each yields: CIELAB **L\*/a\*/b\***, chroma, saturation,
   R/G/B‑to‑photo ratios, and chevron/barring texture — plus optional region‑vs‑region
   contrasts.
3. **Annotate** — paint your regions with a brush; the page grey‑world white‑balances the
   image and computes your measurements live, per bird.
4. **Analyse** — builds the feature matrix and runs an in‑browser **PCA** coloured by
   species (**between‑species**) or individual (**within‑species**), with convex hulls,
   Cohen's *d* / AUC / silhouette, **ICC repeatability**, and a per‑photo ↔ per‑individual
   aggregation toggle.
5. **Map** — plots each bird at its coordinates (Leaflet + OpenStreetMap), coloured by
   species or by any feature / PC score, to reveal biogeographic structure.

Exports: feature‑matrix CSV, annotations JSON, and the PCA as a PNG. Your work persists in
the browser (`localStorage`).

## Why it needs a tiny backend

Macaulay's image CDN does not send CORS headers, so a browser `<canvas>` drawn from one of
its images becomes *tainted* and its pixels can't be read — which would make in‑browser
colour analysis impossible. This app serves the page **and** proxies the images from the
**same origin**, which removes the taint. The colour maths (grey‑world white balance,
sRGB→CIELAB, region statistics, PCA) all still run client‑side; **no images are stored on
the server** (only a small in‑memory cache for the session).

The backend also solves the Macaulay search API's Anubis proof‑of‑work challenge and looks
up eBird taxon codes, so the browser never has to.

## Run locally

```bash
pip install -r requirements.txt
cp .env.example .env        # then edit the values
python app.py               # http://127.0.0.1:8731/
```

If your local Python can't validate Cornell's TLS chain, set `ML_SSL_VERIFY=0` in `.env`.

## Deploy on Railway (via GitHub)

1. Push this folder to a new GitHub repo (see below).
2. In [Railway](https://railway.app): **New Project → Deploy from GitHub repo**, pick the repo.
3. Nixpacks builds it automatically (`railway.toml` sets the start command and `/healthz`
   health check). Add the environment variables:

   | Variable | Purpose |
   |----------|---------|
   | `WORKBENCH_PASSWORD` | shared password gating the page (**required in production**) |
   | `SECRET_KEY` | Flask session signing key — a long random hex string |
   | `EBIRD_API_KEY` | *(optional)* your own eBird API key |
   | `ML_SSL_VERIFY` | *(optional)* leave unset/`1` on Railway |

4. Railway gives the service a public URL. **Link it from your dashboard** with a normal
   anchor, e.g. `<a href="https://your-workbench.up.railway.app" target="_blank">Plumage Workbench</a>`.

Every push to the default branch redeploys automatically.

## Create the GitHub repo

```bash
git init && git add . && git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<you>/plumage-workbench.git
git push -u origin main
```

## Notes & attribution

- Photos and data come from the **Macaulay Library, Cornell Lab of Ornithology**, and
  **eBird**. Respect their terms of use; keep query volumes reasonable (the app throttles
  and caches to help). Get a free eBird API key at <https://ebird.org/api/keygen>.
- Measurements are computed on browser‑decoded images, so values are **comparable within a
  session** but not bit‑identical to an offline Python/PIL pipeline.

## License

[MIT](LICENSE) © 2026 Simon Mitchell
