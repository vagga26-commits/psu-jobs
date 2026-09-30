#!/usr/bin/env python3
"""Fetch the detail (JD) page for every aggregator job and store it in data/jd.json.

data/jd.json maps article URL -> cleaned JD (see jd.clean_jd). Already-fetched
URLs are skipped, so each run only fetches new notices. Also merges any
hand-collected snapshot files in data/jd/*.json.
"""
import glob
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from crawl import fetch  # noqa: E402  (robots.txt + retries + UA)
from jd import clean_jd  # noqa: E402
from parsers.article import parse_article  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "jd.json"


def main():
    store = json.loads(STORE.read_text()) if STORE.exists() else {}
    for f in sorted(glob.glob(str(ROOT / "data" / "jd" / "*.json"))):
        for url, raw in json.loads(Path(f).read_text()).items():
            if url not in store:
                c = clean_jd(raw)
                if c:
                    store[url] = c
    jobs = json.loads((ROOT / "data" / "jobs.json").read_text())["jobs"]
    todo = sorted({j["url"] for j in jobs if j.get("url") and "official" not in j.get("source_types", []) and j["url"] not in store})
    got = 0
    for url in todo:
        html = fetch(url)
        if html:
            c = clean_jd(parse_article(html, url))
            if c:
                store[url] = c
                got += 1
        time.sleep(1.5)
    STORE.write_text(json.dumps(store, ensure_ascii=False, indent=1))
    print(f"jd: {len(store)} stored, {got} fetched now, {len(todo) - got} failed")


if __name__ == "__main__":
    main()
