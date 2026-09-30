"""Header-driven table parser for aggregator listing pages.

Finds every <table> whose header row mentions both a post/title column and a
last-date column, maps columns by header name (so column order changes don't
break it), and yields raw row dicts.
"""
from urllib.parse import urljoin

from bs4 import BeautifulSoup

COLS = {
    "post_date": ("post date", "posted", "date of post", "start date"),
    "org": ("recruitment board", "organization", "organisation", "company", "board", "department"),
    "title": ("post name", "post", "name of post", "title", "vacancy"),
    "qualification": ("qualification", "eligibility", "education"),
    "last_date": ("last date", "closing date", "end date"),
    "advt": ("advt", "advertisement"),
}


def _map_headers(cells):
    mapping = {}
    for i, c in enumerate(cells):
        h = c.lower().strip()
        for field, keys in COLS.items():
            if field not in mapping and any(k in h for k in keys):
                mapping[field] = i
                break
    return mapping


def parse_table(html, base_url):
    soup = BeautifulSoup(html, "lxml")
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        head = [c.get_text(" ", strip=True) for c in rows[0].find_all(["th", "td"])]
        m = _map_headers(head)
        if "title" not in m or "last_date" not in m:
            continue
        for tr in rows[1:]:
            tds = tr.find_all(["td", "th"])
            if len(tds) < len(m):
                continue
            get = lambda f: tds[m[f]].get_text(" ", strip=True) if f in m and m[f] < len(tds) else ""
            link = None
            for a in tr.find_all("a", href=True):
                link = urljoin(base_url, a["href"])  # last link is usually "Get Details"
            row = {f: get(f) for f in COLS}
            row["url"] = link
            if row["title"]:
                yield row
