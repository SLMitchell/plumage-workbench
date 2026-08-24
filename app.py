# -*- coding: utf-8 -*-
"""
Plumage Workbench — a self-contained Flask app.

Query any two eBird taxa from the Macaulay Library, define your own regions and
colour/texture measurements on any part of the bird, annotate the pulled images,
then get a live in-browser PCA and a geographic map of the variation.

Why this needs a backend at all: Macaulay's image CDN sends no CORS headers, so a
browser canvas drawn from an ML image is "tainted" and its pixels can't be read.
Serving the page AND proxying the images from the same origin removes the taint,
so all the colour maths can run client-side. No images are stored server-side.

Routes:
  GET  /                    -> the workbench page (password-gated)
  GET  /login  POST /login  -> shared-password gate
  GET  /logout
  GET  /healthz             -> Railway health check (open)
  GET  /api/taxon?q=        -> eBird taxon autocomplete  [{code,name,sci}]
  GET  /api/search?taxon=&age=&count=&sort=  -> Macaulay media search
  GET  /img/<assetId>/<size>                 -> Cornell CDN image, same-origin

Config via environment:
  WORKBENCH_PASSWORD  shared password. If unset, the app runs OPEN (dev only) and warns.
  SECRET_KEY          Flask session signing key (random per-boot if unset).
  EBIRD_API_KEY       eBird API key for taxon lookup (defaults to the public web key).
  ML_SSL_VERIFY       "0" to disable TLS verification (some local Python builds need this).
  IMG_CACHE_MAX       max images held in the in-memory cache (default 800).
"""
import os
import secrets
import threading
import time

import requests
from flask import (Flask, Response, request, session, redirect, url_for,
                   send_from_directory, jsonify, abort)

from ml_client import MLClient, SEARCH, VERIFY

HERE = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

PASSWORD = os.environ.get("WORKBENCH_PASSWORD", "").strip()
if not PASSWORD:
    app.logger.warning("WORKBENCH_PASSWORD is not set — running OPEN (no auth). "
                       "Set it in production (Railway variables).")

EBIRD_KEY = os.environ.get("EBIRD_API_KEY", "jfekjedvescr")
EBIRD_FIND = "https://api.ebird.org/v2/ref/taxon/find"
CDN = "https://cdn.download.ams.birds.cornell.edu/api/v1/asset/{aid}/{size}"
ALLOWED_SIZES = {320, 480, 640, 900, 1200, 1800, 2400}
IMG_CACHE_MAX = int(os.environ.get("IMG_CACHE_MAX", "800"))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

_sess = requests.Session()
_sess.headers.update({"User-Agent": UA})
_sess.verify = VERIFY

_ml = MLClient()
_ml_lock = threading.Lock()
_last_search = [0.0]          # simple politeness throttle for ML search
_img_cache = {}
_img_lock = threading.Lock()


def _warm_ml():
    """Solve the Macaulay Anubis challenge once at boot so the first real pull
    (and the status probe) doesn't pay the handshake cost."""
    try:
        with _ml_lock:
            _ml.get_json(SEARCH, {"taxonCode": "rutshr2", "mediaType": "photo",
                                  "count": 1}, timeout=25)
    except Exception:
        pass


threading.Thread(target=_warm_ml, daemon=True).start()

KEEP = ["assetId", "speciesCode", "comName", "sciName", "ageClass",
        "rating", "ratingCount", "width", "height",
        "obsDt", "obsYear", "obsMonth", "obsDay", "obsTime",
        "ebirdChecklistId", "licenseId", "userDisplayName", "source"]


# ------------------------------------------------------------------ auth gate
OPEN_PATHS = {"/healthz", "/login", "/favicon.ico"}


@app.before_request
def gate():
    if not PASSWORD:
        return
    p = request.path
    if p in OPEN_PATHS or p.startswith("/static/"):
        return
    if session.get("auth"):
        return
    if p.startswith("/api/") or p.startswith("/img/"):
        abort(401)
    return redirect(url_for("login", next=p))


LOGIN_HTML = """<!doctype html><meta charset="utf-8">
<title>Plumage Workbench — sign in</title>
<style>body{font-family:system-ui,sans-serif;background:#14130f;color:#ece6d9;
display:grid;place-items:center;height:100vh;margin:0}
form{background:#1e1c17;border:1px solid #33302a;border-radius:12px;padding:28px;width:300px}
h1{font-size:16px;margin:0 0 16px}input{width:100%;padding:9px;border-radius:8px;
border:1px solid #33302a;background:#100f0c;color:#ece6d9;margin-bottom:12px}
button{width:100%;padding:9px;border-radius:8px;border:0;background:#74b7ac;color:#14130f;
font-weight:700;cursor:pointer}.err{color:#c65b52;font-size:13px;margin-bottom:10px}</style>
<form method="post"><h1>🪶 Plumage Workbench</h1>
{err}<input type="password" name="password" placeholder="password" autofocus>
<button>Enter</button></form>"""


@app.route("/login", methods=["GET", "POST"])
def login():
    err = ""
    if request.method == "POST":
        if secrets.compare_digest(request.form.get("password", ""), PASSWORD):
            session["auth"] = True
            nxt = request.args.get("next") or "/"
            return redirect(nxt if nxt.startswith("/") else "/")
        err = '<div class="err">Incorrect password.</div>'
    return LOGIN_HTML.replace("{err}", err)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/healthz")
def healthz():
    return "ok", 200


# ------------------------------------------------------------------ page
@app.route("/")
def index():
    return send_from_directory(HERE, "workbench.html")


# ------------------------------------------------------------------ taxon
@app.route("/api/taxon")
def api_taxon():
    term = (request.args.get("q", "") or "").strip()
    if len(term) < 2:
        return jsonify([])
    try:
        r = _sess.get(EBIRD_FIND, params={"locale": "en", "cat": "species",
                      "limit": 12, "q": term, "key": EBIRD_KEY}, timeout=15)
    except Exception as e:
        return jsonify({"error": "eBird unreachable: " + str(e)[:150]}), 502
    data = r.json() if r.text.strip().startswith("[") else []
    out = []
    for d in data:
        nm = d.get("name", "")
        com, _, sci = nm.partition(" - ")
        out.append({"code": d.get("code"), "name": com or nm, "sci": sci})
    return jsonify(out)


# Lightweight connectivity probe for eBird / Macaulay search / image CDN.
# Cached briefly so page loads don't hammer the upstreams.
_status_cache = [0.0, None]


@app.route("/api/status")
def api_status():
    now = time.time()
    if _status_cache[1] is not None and now - _status_cache[0] < 60:
        return jsonify(_status_cache[1])
    out = {}
    try:
        r = _sess.get(EBIRD_FIND, params={"locale": "en", "cat": "species",
                      "limit": 1, "q": "robin", "key": EBIRD_KEY}, timeout=6)
        out["ebird"] = (r.status_code == 200)
    except Exception as e:
        out["ebird"], out["ebird_err"] = False, str(e)[:150]
    try:
        with _ml_lock:
            j = _ml.get_json(SEARCH, {"taxonCode": "rutshr2",
                                      "mediaType": "photo", "count": 1}, timeout=12)
        out["macaulay"] = isinstance(j, list)
    except Exception as e:
        out["macaulay"], out["macaulay_err"] = False, str(e)[:150]
    try:
        r = _sess.get(CDN.format(aid="237720701", size=320), timeout=6)
        out["cdn"] = (r.status_code == 200)
    except Exception as e:
        out["cdn"], out["cdn_err"] = False, str(e)[:150]
    out["ok"] = all(out.get(k) for k in ("ebird", "macaulay", "cdn"))
    _status_cache[0], _status_cache[1] = now, out
    return jsonify(out)


# ------------------------------------------------------------------ search
def _trim(item):
    loc = item.get("location") or {}
    out = {k: item.get(k) for k in KEEP}
    out["countryName"] = loc.get("countryName")
    out["countryCode"] = loc.get("countryCode")
    out["subnational1Name"] = loc.get("subnational1Name")
    out["subnational2Name"] = loc.get("subnational2Name")
    out["locName"] = loc.get("name")
    out["latitude"] = loc.get("latitude")
    out["longitude"] = loc.get("longitude")
    ageSex = item.get("ageSex") or {}
    out["ageSexTag"] = ";".join(k for k, v in ageSex.items() if v)
    return out


def search_taxon(taxon, ages, count, sort):
    rows, seen = [], set()
    ages = ages or [None]
    for age in ages:
        cursor = None
        while len(rows) < count:
            params = {"taxonCode": taxon, "mediaType": "photo",
                      "count": min(100, count), "sort": sort}
            if age:
                params["age"] = age
            if cursor:
                params["initialCursorMark"] = cursor
            with _ml_lock:
                gap = time.time() - _last_search[0]
                if gap < 0.4:
                    time.sleep(0.4 - gap)
                j = _ml.get_json(SEARCH, params)
                _last_search[0] = time.time()
            if not isinstance(j, list) or not j:
                break
            new = 0
            for it in j:
                aid = it.get("assetId")
                if aid in seen:
                    continue
                seen.add(aid)
                rows.append(_trim(it))
                new += 1
            last = j[-1].get("cursorMark")
            if new == 0 or not last or last == cursor or len(j) < params["count"]:
                break
            cursor = last
    return rows[:count]


@app.route("/api/search")
def api_search():
    taxon = (request.args.get("taxon", "") or "").strip()
    if not taxon:
        return jsonify({"error": "taxon required"}), 400
    ages = [a for a in request.args.get("age", "").split(",") if a] or None
    count = max(1, min(500, int(request.args.get("count", "60"))))
    sort = request.args.get("sort", "rating_rank_desc")
    try:
        rows = search_taxon(taxon, ages, count, sort)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"taxon": taxon, "n": len(rows), "assets": rows})


# ------------------------------------------------------------------ image proxy
@app.route("/img/<aid>/<int:size>")
def img(aid, size):
    if not aid.isdigit():
        abort(400)
    if size not in ALLOWED_SIZES:
        size = min(ALLOWED_SIZES, key=lambda s: abs(s - size))
    key = f"{aid}/{size}"
    with _img_lock:
        cached = _img_cache.get(key)
    if cached is None:
        r = _sess.get(CDN.format(aid=aid, size=size), timeout=60)
        if r.status_code != 200:
            abort(r.status_code)
        cached = r.content
        with _img_lock:
            if len(_img_cache) > IMG_CACHE_MAX:
                _img_cache.clear()
            _img_cache[key] = cached
    return Response(cached, mimetype="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8731"))
    app.run(host="127.0.0.1", port=port, debug=True)
