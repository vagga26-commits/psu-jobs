#!/usr/bin/env python3
"""Download a logo (site icon) for every employer domain in data/jobs.json.

Saves data/logos/<domain>.png. build_site.py embeds these into the page so logos
show even where the page can't load images from other sites. Runs in CI after
crawl.py; safe to re-run (existing files are kept for 30 days).
"""
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "logos"
SRC = "https://www.google.com/s2/favicons?domain={d}&sz=128"
MAX_AGE = 30 * 86400


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = json.loads((ROOT / "data" / "jobs.json").read_text())["jobs"]
    domains = sorted({j["logo_domain"] for j in jobs if j.get("logo_domain")})
    ok = 0
    for d in domains:
        f = OUT / f"{d}.png"
        if f.exists() and time.time() - f.stat().st_mtime < MAX_AGE:
            ok += 1
            continue
        try:
            r = requests.get(SRC.format(d=d), timeout=20)
            # Google answers unknown sites with a 16px globe; skip those
            if r.ok and r.headers.get("content-type", "").startswith("image/") and len(r.content) > 400:
                f.write_bytes(r.content)
                ok += 1
        except requests.RequestException as e:
            print(f"{d}: {e}")
        time.sleep(0.2)
    print(f"logos: {ok}/{len(domains)} domains")


if __name__ == "__main__":
    main()
