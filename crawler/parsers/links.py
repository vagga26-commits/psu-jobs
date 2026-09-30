"""Parser for aggregator pages that list notices as links, not tables.

SarkariResult, SarkariExam, Sarkari Naukri Blog and similar sites publish
"Latest Jobs" as lists of titles like

    "SSC CHSL 10+2 Online Form 2026 (2536 Posts)"
    "Bihar BTSC Touring Veterinary Officer Online Form 2026"
    "Bank of India Specialist Officer SO Online Form 2026 – Extend"

`parse_links` pulls those anchors (with any "Last Date: …" text next to them)
and `split_title` turns a title into organisation, post and vacancies. Rows
without a last date are completed later from the detail page (crawl.py).
"""
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

JOB_WORDS = re.compile(r"online form|recruitment|vacancy|vacancies|bharti|apply|notification|offline form|walk[\s-]?in|posts?\b", re.I)
NOT_JOBS = re.compile(r"\b(result|admit card|answer key|syllabus|cut[\s-]?off|merit list|exam date|exam city|status|"
                      r"option form|correction|score card|interview letter|scholarship|otr|one time registration|admission)\b", re.I)
LAST = re.compile(r"last\s*date\s*[:\-–]?\s*([0-9]{1,2}[\s./-][A-Za-z0-9]{2,9}[\s./-][0-9]{2,4})", re.I)

# prefixes that aggregators put before a board name ("Bihar BTSC", "Railway RRB")
PLACE_PREFIX = re.compile(r"^(bihar|jharkhand|rajasthan|railway|haryana|punjab|uttarakhand|uk|mp|up|delhi|assam|odisha|"
                          r"gujarat|karnataka|kerala|telangana|tamil nadu|tn|west bengal|wb|himachal pradesh|hp)\s+(?=(?-i:[A-Z][A-Z0-9]+)\b)", re.I)
FAMILY = {"CSIR", "DRDO", "ISRO", "ICAR", "AIIMS", "IIT", "NIT", "IIIT", "IIM", "ICMR", "ESIC", "GIMS", "NHM", "DHS",
          "WCD", "DLSA", "SAIL", "RRC", "CMHO", "DMHO", "ECHS", "KGBV"}
ACRO = re.compile(r"^[A-Z][A-Z0-9&]{1,9}$")
SUFFIX = re.compile(r"\s*[–—-]\s*(extend(ed)?|start|re-?open|update[d]?|last date|postponed|cancelled|out)\s*$|\s*\((update|updated|postponed|extended)\)\s*$", re.I)
FORM = re.compile(r"\b(online|offline)\s+form\b.*$|\brecruitment\b.*$|\bnotification\b.*$|\bvacancy\b.*$|\bbharti\b.*$", re.I)
VAC = re.compile(r"\(?\s*([\d,]{1,7})\s*posts?\s*\)?", re.I)
ORG_END = re.compile(r"\b(apprentices?|assistant|officer|officers|constable|teacher|engineer|clerk|manager|trainee|"
                     r"technician|nurse|staff|executive|consultant|professor|lecturer|inspector|pharmacist|librarian|"
                     r"driver|operator|scientist|fellow|non[\s-]teaching|teaching|various|group|head|junior|senior|"
                     r"specialist|medical|security|sub|sports|so|po|mt|ao|je|si|gd|tgc|chsl|cgl|mts|ntpc|pgt|tgt|prt|non|sco|post|posts|"
                     r"primary|school|sanitary|safai|anganwadi|upper|lower|combined|engineering|civil|computer|food|"
                     r"dental|hindi|paramedical|technical|tradesman|fishery|fisheries|touring|veterinary|livestock|"
                     r"trade|graduate|10\+2|inter|special|spa|pa|agniveer|jr|sr|dy|deputy|chief|general|"
                     r"skilled|multi|data|accounts?|stenographer|steno|typist|lab|field|project|research|jrf|srf)\b", re.I)


def split_title(title):
    """'Bihar BTSC Touring Veterinary Officer Online Form 2026' -> ('BTSC', 'Touring Veterinary Officer', None)."""
    t = re.sub(r"\s+", " ", title).strip()
    t = SUFFIX.sub("", t)
    vac = None
    m = VAC.search(t)
    if m:
        try:
            vac = int(m.group(1).replace(",", ""))
        except ValueError:
            vac = None
        t = (t[:m.start()] + t[m.end():]).strip()
    t = FORM.sub("", t).strip(" -–—,:")
    t = re.sub(r"\b\d{1,2}/20\d\d\b", "", t)
    t = re.sub(r"\b20\d\d(-\d\d)?\b", "", t).strip(" -–—,:")
    t = PLACE_PREFIX.sub("", t)
    words = t.split()
    if not words:
        return title, title, vac
    # organisation = leading words until a post word, keeping multi-word names ("Bank of India", "Indian Army")
    cut = len(words)
    if ACRO.match(words[0]) and len(words) > 1 and words[0] not in {"MP", "UP", "HP", "UK", "TN", "WB", "AP", "J&K"}:
        # board acronyms: "SSC CHSL", "RRB NTPC", "MPESB Subedar" -> org is the first word;
        # families keep their campus/lab: "AIIMS Bhopal", "CSIR NGRI"
        cut = 2 if words[0] in FAMILY else 1
        words_org = " ".join(words[:cut])
        post = " ".join(words[cut:]).strip(" ,") or words_org
        return words_org, post, vac
    for i, w in enumerate(words):
        if i > 0 and ORG_END.fullmatch(w.strip("(),/")):
            cut = i
            break
    # an acronym followed by more acronyms is still the org ("CSIR NGRI", "MPESB MP Police" stops at Police)
    org = " ".join(words[:cut]).strip(" ,/")
    post = " ".join(words[cut:]).strip(" ,") or org
    return org or title, post, vac


def parse_links(html, base_url, include=None, exclude=None):
    soup = BeautifulSoup(html, "lxml")
    main = soup.find("main") or soup.find(id=re.compile("content|main", re.I)) or soup.body or soup
    inc = re.compile(include, re.I) if include else None
    exc = re.compile(exclude, re.I) if exclude else None
    host = urlparse(base_url).netloc
    seen = set()
    for a in main.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        href = urljoin(base_url, a["href"])
        if href in seen or len(text) < 12 or urlparse(href).netloc != host:
            continue
        if not JOB_WORDS.search(text) or NOT_JOBS.search(text):
            continue
        if (inc and not inc.search(href + " " + text)) or (exc and exc.search(href + " " + text)):
            continue
        seen.add(href)
        ctx = a.find_parent(["li", "tr", "article", "div", "p"])
        ctx_text = ctx.get_text(" ", strip=True) if ctx and len(ctx.get_text(strip=True)) < 400 else text
        lm = LAST.search(ctx_text)
        org, post, vac = split_title(text)
        yield {"org": org, "title": post + (f" – {vac} Posts" if vac else ""), "qualification": "",
               "post_date": "", "last_date": lm.group(1) if lm else "", "url": href, "raw_title": text}
