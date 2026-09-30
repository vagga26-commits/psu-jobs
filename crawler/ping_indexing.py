#!/usr/bin/env python3
"""Tell search engines about new and removed job pages right after each deploy.

Job notices live for days, so waiting for a normal crawl loses most of the
traffic. This script compares dist/sitemap.xml with the last run's URL list
(data/published_urls.json) and notifies:

  * IndexNow (Bing, Yandex, Seznam, Naver) – set INDEXNOW_KEY (any 8–128 hex/alnum
    string). build_site.py writes the key file into dist/ so engines can verify it.
  * Google Indexing API (officially supported for JobPosting pages) – set
    GOOGLE_INDEXING_SA to a service-account JSON that is an Owner of the site
    in Google Search Console. Needs `pip install google-auth requests`.

Both are optional; with neither set it only records the URL list.
Run it AFTER the site is deployed so the URLs resolve.
"""
import json
import os
import re
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
STATE = ROOT / "data" / "published_urls.json"
GOOGLE_DAILY_QUOTA = 200  # default Indexing API quota


def current_urls():
    xml = (DIST / "sitemap.xml").read_text()
    return re.findall(r"<loc>([^<]+)</loc>", xml)


def indexnow(urls, key, host):
    if not urls:
        return 0
    body = {"host": host, "key": key, "keyLocation": f"https://{host}/{key}.txt", "urlList": urls[:10000]}
    r = requests.post("https://api.indexnow.org/indexnow", json=body, timeout=30)
    print(f"IndexNow: {len(urls)} URLs -> HTTP {r.status_code}")
    return len(urls)


def google(updated, deleted, sa_json):
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account
    creds = service_account.Credentials.from_service_account_info(
        json.loads(sa_json), scopes=["https://www.googleapis.com/auth/indexing"])
    s = AuthorizedSession(creds)
    sent = 0
    for url, kind in [(u, "URL_UPDATED") for u in updated] + [(u, "URL_DELETED") for u in deleted]:
        if sent >= GOOGLE_DAILY_QUOTA:
            print("Google: daily quota reached, rest will go next run")
            break
        r = s.post("https://indexing.googleapis.com/v3/urlNotifications:publish", json={"url": url, "type": kind})
        sent += 1
        if r.status_code >= 400:
            print(f"Google {kind} {url}: HTTP {r.status_code} {r.text[:120]}")
    print(f"Google Indexing API: {sent} notifications")


def main():
    now = current_urls()
    before = json.loads(STATE.read_text()) if STATE.exists() else []
    jobs_now = [u for u in now if "/job/" in u]
    new = [u for u in now if u not in set(before)]
    gone = [u for u in before if u not in set(now) and "/job/" in u]
    print(f"{len(now)} URLs ({len(jobs_now)} job pages); {len(new)} new, {len(gone)} removed")

    key = os.environ.get("INDEXNOW_KEY")
    if key and now:
        host = re.sub(r"^https?://([^/]+).*", r"\1", now[0])
        # changed = new + removed + list pages that change every run
        lists = [u for u in now if "/job/" not in u]
        indexnow(new + gone + lists[:50], key, host)
    sa = os.environ.get("GOOGLE_INDEXING_SA")
    if sa:
        google([u for u in new if "/job/" in u], gone, sa)
    STATE.write_text(json.dumps(now, indent=0))


if __name__ == "__main__":
    main()
