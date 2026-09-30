#!/usr/bin/env python3
"""Crawl configured sources and write data/jobs.json.

Usage:
  python crawler/crawl.py                 # crawl everything
  python crawler/crawl.py --snapshot data/snapshot.tsv   # also merge a manual TSV
  python crawler/crawl.py --only aggregators
"""
import argparse
import re
import csv
import json
import logging
import os
import sys
import time
import urllib.robotparser
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from normalize import is_open, merge, normalize  # noqa: E402
from parsers import parse_official, parse_table  # noqa: E402
from parsers.links import parse_links  # noqa: E402
from parsers.article import parse_article  # noqa: E402
from jd import clean_jd  # noqa: E402
from normalize import parse_date  # noqa: E402

LAST_KEY = re.compile(r"last|closing|end|close", re.I)
START_KEY = re.compile(r"start|notification|opening|begin|publish|post", re.I)


def dates_from_jd(jd):
    """Pick the last date and posting date out of a detail page's Important Dates."""
    last = posted = None
    for k, v in (jd or {}).get("dates", {}).items():
        d = parse_date(str(v))
        if not d:
            continue
        if LAST_KEY.search(k) and not re.search(r"fee|correction|admit|exam", k, re.I):
            last = max(last, d) if last else d
        elif START_KEY.search(k) and not posted:
            posted = d
    return last, posted

ROOT = Path(__file__).resolve().parent.parent
JD_STORE = ROOT / "data" / "jd.json"
UA = "PSUJobsBot/1.0 (+https://github.com/your-org/psu-jobs; job-listing aggregator)"
log = logging.getLogger("crawl")

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9"})
_robots = {}


def allowed(url):
    host = urlparse(url)
    base = f"{host.scheme}://{host.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser(base + "/robots.txt")
        try:
            rp.read()
        except Exception:
            rp = None  # unreachable robots.txt -> allow
        _robots[base] = rp
    rp = _robots[base]
    return rp is None or rp.can_fetch(UA, url)


def fetch(url, retries=3):
    if not allowed(url):
        log.warning("robots.txt disallows %s", url)
        return None
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 200:
                r.encoding = r.apparent_encoding or r.encoding
                return r.text
            log.warning("%s -> HTTP %s", url, r.status_code)
            if r.status_code in (403, 404):
                return None
        except requests.RequestException as e:
            log.warning("%s -> %s", url, e)
        time.sleep(2 ** attempt)
    return None


def load_snapshot(path):
    """TSV with header: post_date org title qualification last_date url"""
    with open(path, newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f, delimiter="\t")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", action="append", default=[], help="extra TSV of rows to merge (repeatable)")
    ap.add_argument("--only", choices=["aggregators", "official", "snapshot"], help="snapshot = no network, merge --snapshot files only")
    ap.add_argument("--out", default=str(ROOT / "data" / "jobs.json"))
    ap.add_argument("--keep-expired-days", type=int, default=0)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    cfg = yaml.safe_load((Path(__file__).parent / "sources.yaml").read_text())
    today = date.fromisoformat(os.environ["TODAY"]) if os.environ.get("TODAY") else date.today()
    records, status = [], []

    jd_store = json.loads(JD_STORE.read_text()) if JD_STORE.exists() else {}
    if args.only not in ("official", "snapshot"):
        for src in cfg.get("aggregators", []):
            if src.get("enabled") is False:
                continue
            html = fetch(src["url"])
            n = 0
            if html:
                rows = parse_table(html, src["url"]) if src.get("parser", "table") == "table" else \
                    parse_links(html, src["url"], src.get("include"), src.get("exclude"))
                fetched = 0
                for row in rows:
                    if not row.get("last_date"):
                        # link lists often carry no dates: take them from the detail page (cached)
                        jd = jd_store.get(row["url"])
                        if jd is None and fetched < src.get("detail_limit", 40):
                            page = fetch(row["url"])
                            fetched += 1
                            jd = clean_jd(parse_article(page, row["url"])) if page else None
                            if jd:
                                jd_store[row["url"]] = jd
                            time.sleep(1.0)
                        last, posted = dates_from_jd(jd)
                        if not last:
                            continue
                        row["last_date"] = last.strftime("%d-%m-%Y")
                        row["post_date"] = row.get("post_date") or (posted.strftime("%d-%m-%Y") if posted else "")
                    row.setdefault("category", src.get("category"))
                    row["state"] = row.get("state") or src.get("state", "")
                    rec = normalize(row, src["name"], src.get("only_known_orgs", False), today)
                    if rec:
                        records.append(rec)
                        n += 1
            status.append({"source": src["name"], "kind": "aggregator", "url": src["url"], "ok": bool(html), "rows": n})
            log.info("%-28s %4d rows", src["name"], n)
            time.sleep(1.5)

        JD_STORE.write_text(json.dumps(jd_store, ensure_ascii=False, indent=1))

    if args.only not in ("aggregators", "snapshot"):
        for src in cfg.get("official", []):
            if src.get("enabled") is False:
                continue
            html = fetch(src["url"])
            n = 0
            if html:
                for row in parse_official(html, src["url"], src["org"]):
                    rec = normalize(row, f"{src['org']} careers", False, today, kind="official")
                    if rec:
                        records.append(rec)
                        n += 1
            status.append({"source": f"{src['org']} careers", "kind": "official", "url": src["url"], "ok": bool(html), "rows": n})
            log.info("%-28s %4d rows", src["org"], n)
            time.sleep(1.5)

    if args.snapshot:
        counts = {}
        for row in (r for path in args.snapshot for r in load_snapshot(path)):
            rec = normalize(row, row.get("source") or "Snapshot", row.get("only_known") == "1", today,
                            kind=row.get("kind") or "aggregator")
            if rec:
                records.append(rec)
            key = (row.get("source") or "Snapshot", row.get("kind") or "aggregator", row.get("source_url") or "")
            counts[key] = counts.get(key, 0) + (1 if rec else 0)
        for (name, kind, url), n in counts.items():
            status.append({"source": name, "kind": kind, "url": url, "ok": True, "rows": n})

    # Carry forward jobs from the previous run so a flaky source doesn't make
    # listings vanish; they drop off naturally once their last date passes.
    prev = []
    if Path(args.out).exists():
        try:
            prev = json.loads(Path(args.out).read_text()).get("jobs", [])
        except ValueError:
            prev = []
    records = [r for r in records if is_open(r, today)]   # closed notices must not merge into open ones
    for r in records:
        r.setdefault("first_seen", today.isoformat())
    jobs = [j for j in merge(prev + records) if is_open(j, today)]
    jobs.sort(key=lambda j: (j["last_date"] or "9999", j["org"]))
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(jobs),
        "sources": status,
        "jobs": jobs,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    log.info("wrote %d open jobs -> %s", len(jobs), args.out)


if __name__ == "__main__":
    main()
