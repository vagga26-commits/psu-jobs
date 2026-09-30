"""Parse an aggregator article (job detail) page into a raw JD dict.

Works on the common layout of Indian job-portal articles: headed sections
("Important Dates", "Application Fee", "Age Limit", "Vacancy Details",
"Eligibility", "Selection Process", "How to Apply") followed by lists, tables
or paragraphs, plus an "Important Links" table whose rows say what each link is.
Output keys match what jd.clean_jd expects.
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

SECTIONS = [
    ("important_dates", r"important dates|dates"),
    ("application_fee", r"application fee|fee"),
    ("age_limit", r"age limit|age"),
    ("vacancy", r"vacancy|post details|posts"),
    ("eligibility", r"eligibility|qualification"),
    ("selection_process", r"selection"),
    ("how_to_apply", r"how to apply|steps to apply"),
    ("pay_scale", r"pay scale|salary|remuneration|stipend"),
]
SECTIONS = [(k, re.compile(rx, re.I)) for k, rx in SECTIONS]
LINK_LABELS = [
    ("apply_online", r"apply online|online application|register|apply now|apply here"),
    ("notification_pdf", r"notification|advertisement|advt"),
    ("application_form", r"application form|download form"),
    ("official_website", r"official website|official site"),
]
LINK_LABELS = [(k, re.compile(rx, re.I)) for k, rx in LINK_LABELS]
HEADING = {"h1", "h2", "h3", "h4", "strong", "b"}


def _section_of(text):
    for key, rx in SECTIONS:
        if rx.search(text) and len(text) < 80:
            return key
    return None


def _lines(node):
    if node.name in ("ul", "ol"):
        return [li.get_text(" ", strip=True) for li in node.find_all("li")]
    if node.name == "table":
        rows = []
        for tr in node.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if any(cells):
                rows.append(cells)
        return rows
    t = node.get_text(" ", strip=True)
    return [t] if t else []


def parse_article(html, base_url):
    soup = BeautifulSoup(html, "lxml")
    out = {"links": {}, "important_dates": {}, "vacancy": []}
    for k, _ in SECTIONS:
        out.setdefault(k, [])

    # Important links: any table row / list item with a label and an <a>
    for row in soup.find_all(["tr", "li", "p"]):
        a = row.find("a", href=True)
        if not a:
            continue
        label = row.get_text(" ", strip=True)
        for key, rx in LINK_LABELS:
            if rx.search(label) and key not in out["links"]:
                out["links"][key] = urljoin(base_url, a["href"])
                break

    # Sections: walk block elements, switching section on headings
    current = None
    body = soup.find("article") or soup.body or soup
    for node in body.find_all(["h1", "h2", "h3", "h4", "p", "ul", "ol", "table", "strong", "b"]):
        if node.find_parent(["ul", "ol", "table"]) and node.name not in ("ul", "ol", "table"):
            continue
        text = node.get_text(" ", strip=True)
        if node.name in HEADING or (node.name == "p" and node.find(["strong", "b"]) and len(text) < 80):
            sec = _section_of(text)
            if sec:
                current = sec
                continue
            if node.name in ("h1", "h2", "h3", "h4"):
                current = None
            continue
        if not current:
            if node.name == "p" and not out.get("summary") and len(text) > 80:
                out["summary"] = text
            continue
        lines = _lines(node)
        if current == "important_dates":
            for ln in lines:
                if isinstance(ln, list) and len(ln) >= 2:
                    out["important_dates"][ln[0]] = ln[1]
                elif isinstance(ln, str) and ":" in ln:
                    k, v = ln.split(":", 1)
                    out["important_dates"][k.strip()] = v.strip()
        elif current == "vacancy":
            for ln in lines:
                if isinstance(ln, list) and len(ln) >= 2 and re.search(r"\d", ln[1]) and not re.search(r"post name", ln[0], re.I):
                    out["vacancy"].append({"post": ln[0], "count": ln[1], "qualification": ln[2] if len(ln) > 2 else None})
        elif current == "pay_scale":
            out["pay_scale"] = " ".join(" ".join(ln) if isinstance(ln, list) else ln for ln in lines) or None
        else:
            out[current] += [" – ".join(ln) if isinstance(ln, list) else ln for ln in lines]
    if isinstance(out.get("pay_scale"), list):
        out["pay_scale"] = None
    return out
