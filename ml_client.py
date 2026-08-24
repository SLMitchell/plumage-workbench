"""
Macaulay Library search client that transparently solves the Anubis
proof-of-work challenge guarding search.macaulaylibrary.org.

The public JSON search API is fronted by Anubis (github.com/TecharoHQ/anubis).
The "fast" challenge requires finding a nonce such that
    sha256(randomData + str(nonce))
has `difficulty` leading zero hex digits. We solve it, hit the
pass-challenge endpoint to obtain the auth cookie, then reuse the
session for real API calls.

SSL verification is configurable: some local Python builds can't validate
Cornell's chain and need verify=False; server hosts (e.g. Railway) validate
fine, so it defaults to True. Set the ML_SSL_VERIFY env var to 0 to disable.
"""
import hashlib
import json
import os
import re
import time

import requests
import urllib3

VERIFY = os.environ.get("ML_SSL_VERIFY", "1") not in ("0", "false", "False", "")
if not VERIFY:
    urllib3.disable_warnings()

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
BASE = "https://search.macaulaylibrary.org"
SEARCH = BASE + "/api/v2/search"


def _solve(random_data, difficulty):
    """Find nonce so sha256(random_data+nonce) has `difficulty` leading zero nibbles."""
    prefix = "0" * difficulty
    nonce = 0
    while True:
        h = hashlib.sha256((random_data + str(nonce)).encode()).hexdigest()
        if h.startswith(prefix):
            return nonce, h
        nonce += 1


class MLClient:
    def __init__(self, verify=VERIFY):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA})
        self.s.verify = verify

    def _pass_challenge(self, html):
        m = re.search(r'<script id="anubis_challenge"[^>]*>(.*?)</script>', html, re.S)
        if not m:
            raise RuntimeError("no anubis challenge found in page")
        data = json.loads(m.group(1))
        chal = data["challenge"]
        diff = chal["difficulty"]
        rnd = chal["randomData"]
        cid = chal["id"]
        t0 = time.time()
        nonce, h = _solve(rnd, diff)
        elapsed = int((time.time() - t0) * 1000)
        return self.s.get(
            BASE + "/.within.website/x/cmd/anubis/api/pass-challenge",
            params={"id": cid, "response": h, "nonce": nonce,
                    "redir": BASE + "/", "elapsedTime": elapsed},
            timeout=60, allow_redirects=True)

    def get_json(self, url, params=None, tries=3, timeout=60):
        for attempt in range(tries):
            r = self.s.get(url, params=params, timeout=timeout)
            ctype = r.headers.get("content-type", "")
            if "application/json" in ctype or (r.text[:1] in "[{"):
                try:
                    return r.json()
                except Exception:
                    pass
            if "anubis" in r.text.lower() or "not a bot" in r.text.lower():
                self._pass_challenge(r.text)
                continue
            try:
                return r.json()
            except Exception:
                if attempt == tries - 1:
                    raise RuntimeError(f"unexpected response ({ctype}): {r.text[:200]}")
        raise RuntimeError("failed to get JSON after solving challenge")


if __name__ == "__main__":
    c = MLClient()
    j = c.get_json(SEARCH, {"taxonCode": "rutshr2", "mediaType": "photo", "count": 3})
    print("ok" if isinstance(j, list) else j)
