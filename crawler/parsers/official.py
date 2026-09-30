"""Heuristic parser for PSU career pages.

PSU sites differ wildly (ASP.NET grids, PDF lists, JS tabs), so rather than a
selector per site we harvest links whose text or URL looks like a recruitment
notice, then look for dates in the surrounding row/list item. Good enough to
surface new notices; the aggregator feed supplies richer structured fields.
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

KEYWORDS = re.compile(
    r"recruit|advertisement|advt|vacanc|engagement|apprentice|walk[\s-]?in|"
    r"trainee|executive|officer|engineer|manager|notification|hiring|posts?\b", re.I)
NOISE = re.compile(r"result|answer key|admit card|corrigendum|archive|tender|login|faq|privacy|"
                   r"empanelment|admission|select(ion)? list|interview schedule|shortlist", re.I)
CLOSED = re.compile(r"\bclosed\b|\bexpired\b", re.I)
ONGOING = re.compile(r"\b(ongoing|active|open till|till filled)\b", re.I)
DATE = re.compile(r"\d{1,2}[\-/.]\d{1,2}[\-/.]\d{2,4}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9},?\s+\d{4}")
LAST = re.compile(r"(last|closing|close|end)\s*date[^0-9A-Za-z]{0,5}", re.I)


def _context(a):
    for parent in a.parents:
        if parent.name in ("tr", "li", "p", "div") and len(parent.get_text(strip=True)) < 600:
            return parent.get_text(" ", strip=True)
    return a.get_text(" ", strip=True)


def parse_official(html, base_url, org):
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        href = urljoin(base_url, a["href"])
        if href in seen or len(text) < 8:
            continue
        if not (KEYWORDS.search(text) or KEYWORDS.search(href)) or NOISE.search(text):
            continue
        seen.add(href)
        ctx = _context(a)
        if CLOSED.search(ctx):
            continue
        dates = DATE.findall(ctx)
        last = None
        lm = LAST.search(ctx)
        if lm:
            after = DATE.search(ctx[lm.end():])
            last = after.group(0) if after else None
        elif len(dates) >= 2:
            last = dates[-1]
        if not last and ONGOING.search(ctx):
            last = "Ongoing"
        yield {
            "org": org,
            "title": text[:200],
            "qualification": "",
            "post_date": dates[0] if dates and dates[0] != last else "",
            "last_date": last or "",
            "url": href,
            "official_url": href,
        }
