"""Turn raw scraped rows into clean, deduplicated job records."""
import hashlib
import json
import re
from datetime import date

from classify import classify
from logos import logo_domain
from orgs import EXCLUDE, resolve

DATE_RE = re.compile(r"(\d{1,2})[\-/.](\d{1,2})[\-/.](\d{2,4})")
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
TEXT_DATE_RE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?[\s\-]+([A-Za-z]{3,9})[\s,\-]+(\d{4})")


def parse_date(s):
    """Parse Indian-style dates (DD-MM-YYYY, DD/MM/YY, '5 Oct 2026')."""
    if not s:
        return None
    m = DATE_RE.search(s)
    if m:
        d, mo, y = map(int, m.groups())
        y += 2000 if y < 100 else 0
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    m = TEXT_DATE_RE.search(s)
    if m and m.group(2)[:3].lower() in MONTHS:
        try:
            return date(int(m.group(3)), MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
        except ValueError:
            return None
    return None


SLUG_VAC = re.compile(r"for-(\d{1,5})-[a-z0-9-]*?(?:posts?|seats|vacancies)(?:-|$)")
TEXT_VAC = re.compile(r"(\d{1,5})\s*(?:posts?|vacanc(?:y|ies)|seats)\b", re.I)


def parse_vacancies(title, url):
    for rx, t in ((TEXT_VAC, title), (SLUG_VAC, (url or "").lower())):
        m = rx.search(t or "")
        if m and 0 < int(m.group(1)) < 100000:
            return int(m.group(1))
    return None


APPLY_RE = re.compile(r"walk[\s-]?in|offline|online", re.I)


def apply_mode(*texts):
    for t in texts:
        m = APPLY_RE.search(t or "")
        if m:
            v = m.group(0).lower().replace("-", "").replace(" ", "")
            return {"walkin": "Walk-in", "offline": "Offline", "online": "Online"}[v]
    return None


def job_id(org, title, last_date, url=None):
    # aggregator articles have one URL per notice, so the URL tells apart two notices with the same
    # title and date on one site; company pages often reuse one URL, so they are keyed on title + date
    basis = f"{org}|{re.sub(r'[^a-z0-9]', '', title.lower())[:60]}|{last_date}" + (f"|{url}" if url else "")
    return hashlib.sha1(basis.encode()).hexdigest()[:12]


CLOSED_RE = re.compile(r"\bclosed\b|\bexpired\b", re.I)
ONGOING_RE = re.compile(r"ongoing|active|open|till filled|continuous", re.I)
UNDATED_MAX_AGE = 45    # days a notice without a last date stays listed after posting
ONGOING_MAX_AGE = 60    # same, when the site marks it Ongoing/Active


def normalize(raw, source, only_known=False, today=None, kind="aggregator"):
    """raw: dict with org, title, qualification, post_date, last_date, url, [official_url].

    kind: "official" for a PSU's own careers site, "aggregator" for job portals.
    """
    today = today or date.today()
    if EXCLUDE.search(raw.get("org", "")):
        return None
    short, full, sector, known = resolve(raw.get("org", ""))
    if only_known and not known:
        return None
    last_txt = raw.get("last_date") or ""
    if CLOSED_RE.search(last_txt):
        return None
    last = parse_date(last_txt)
    posted = parse_date(raw.get("post_date"))
    title = re.sub(r"\s*[–-]\s*\d+\s*posts?$", "", raw.get("title", "").strip(), flags=re.I)
    url = raw.get("url") or raw.get("official_url")
    level, dept, _ = classify(raw.get("org", ""), title, raw.get("category"))
    state = (raw.get("state") or "").strip()
    rec = {
        "id": job_id(short, title, last, url if kind == "aggregator" else None),
        "org": short,
        "org_full": full,
        "sector": sector if known else None,
        "level": level,
        "department": dept,
        "locations": [state] if state and state != "All India" else ["All India"],
        "logo_domain": logo_domain(short),
        "title": title,
        "qualification": [q.strip() for q in re.split(r",|/(?=\s)", raw.get("qualification") or "") if q.strip()],
        "vacancies": parse_vacancies(raw.get("title"), raw.get("url")),
        "apply_mode": apply_mode(raw.get("url"), raw.get("title")),
        "posted": posted.isoformat() if posted else None,
        "last_date": last.isoformat() if last else None,
        "status": "Ongoing" if not last and ONGOING_RE.search(last_txt) else None,
        "url": url,
        "sources": [source],
        "hosts": [_site(url)],
        "source_types": [kind],
    }
    if kind == "official":
        rec["official_url"] = raw.get("official_url") or url
    elif raw.get("official_url"):
        rec["official_url"] = raw["official_url"]
    return rec


STOP = set("""a an and the of for in on at to by with or more posts post basis contract contractual regular
engagement recruitment recruit various vacancy vacancies notification advt advertisement through
fixed term tenure unit region division directorate""".split())


def _tokens(title):
    toks = re.findall(r"[a-z]+", title.lower())
    return {t[:-1] if t.endswith("s") and len(t) > 3 else t for t in toks if t not in STOP and len(t) > 1}


COMMON = set("""officer assistant manager engineer apprentice teacher clerk constable trainee technician nurse staff
executive consultant professor lecturer inspector pharmacist driver operator junior senior deputy chief general
head medical group non teaching specialist""".split())
GENERIC = re.compile(r"^(various|various posts?|multiple posts?|posts?|recruitment|vacancies|jobs)$", re.I)


def _site(u):
    return re.sub(r"^https?://(www\.)?([^/]+).*", r"\2", u or "").lower()


def _org_words(r):
    return {w for w in re.findall(r"[a-z0-9]+", f"{r['org']} {r.get('org_full') or ''}".lower()) if w not in STOP and len(w) > 1}


def _org_match(a, b):
    if a["org"] == b["org"]:
        return True
    # both are organisations we know (e.g. SBI vs Bank of India): names must agree exactly
    if resolve(a["org"])[3] and resolve(b["org"])[3]:
        return resolve(a["org"])[0] == resolve(b["org"])[0]
    oa, ob = _org_words(a), _org_words(b)
    if not oa or not ob:
        return False
    alla = oa | _tokens(a["title"])
    allb = ob | _tokens(b["title"])
    return oa <= allb or ob <= alla


def _days_apart(a, b):
    la, lb = a.get("last_date"), b.get("last_date")
    if not (la and lb):
        return None
    return abs((date.fromisoformat(la) - date.fromisoformat(lb)).days)


def _same_notice(a, b):
    """Fuzzy match of one notice listed on two different sites.

    Different sites word the same notice differently ("SSC CHSL 10+2 Online Form
    2026 (2536 Posts)" vs "CHSL – 2536 Posts"), and deadlines get extended, so we
    combine several signals: organisation, vacancy count, last date, title words.
    Notices from the same site are never fuzzy-merged (they're distinct notices).
    """
    if set(a.get("hosts") or [_site(a.get("url"))]) & set(b.get("hosts") or [_site(b.get("url"))]):
        return False
    ta, tb = _tokens(a["title"]), _tokens(b["title"])
    generic = not ta or not tb or GENERIC.match(" ".join(sorted(ta))) or GENERIC.match(" ".join(sorted(tb)))
    overlap = len(ta & tb) / min(len(ta), len(tb)) if ta and tb else 0.0
    org = _org_match(a, b)
    gap = _days_apart(a, b)
    close = gap is None or gap <= 21
    same_day = gap == 0
    va, vb = a.get("vacancies"), b.get("vacancies")
    same_vac = bool(va and vb and va == vb)
    pa, pb = a.get("posted"), b.get("posted")
    if org and same_vac and close:
        return True
    if org and same_day and (overlap >= 0.4 or generic):
        return True
    if org and pa and pb and pa == pb and overlap >= 0.5 and gap is None:
        return True  # an undated company-site row and a dated portal row posted the same day
    if org and overlap >= 0.75 and close and min(len(ta), len(tb)) >= 2:
        return True
    if org and close and ta and tb and min(len(ta), len(tb)) == 1 and overlap == 1.0 and not (ta & tb & COMMON):
        return True  # "Indian Army TGC 145" vs "Technical Graduate Course (TGC-145) Officer"
    if same_day and overlap == 1.0 and min(len(ta), len(tb)) >= 2:
        return True  # "UP Special TET" vs "UPESSC Special Teacher Eligibility Test (Special TET)"
    if same_vac and va >= 100 and close and overlap >= 0.34:
        return True
    if same_vac and va >= 1000 and close:
        return True
    return False


def _absorb(cur, r):
    cur["sources"] = sorted(set(cur["sources"]) | set(r["sources"]))
    cur["hosts"] = sorted(set(cur.get("hosts") or [_site(cur.get("url"))]) | set(r.get("hosts") or [_site(r.get("url"))]))
    # deadline extended on one site -> keep the later date
    if cur.get("last_date") and r.get("last_date") and r["last_date"] > cur["last_date"]:
        cur["last_date"] = r["last_date"]
    # keep the more specific title
    if GENERIC.match(" ".join(sorted(_tokens(cur["title"])))) and not GENERIC.match(" ".join(sorted(_tokens(r["title"])))):
        cur["title"] = r["title"]
    cur.setdefault("also_urls", [])
    if r.get("url") and r["url"] != cur.get("url") and r["url"] not in cur["also_urls"]:
        cur["also_urls"].append(r["url"])
    cur["source_types"] = sorted(set(cur.get("source_types", ["aggregator"])) | set(r.get("source_types", ["aggregator"])))
    for k in ("vacancies", "apply_mode", "posted", "official_url", "last_date", "first_seen"):
        if not cur.get(k) and r.get(k):
            cur[k] = r[k]
    if cur.get("last_date"):
        cur["status"] = None
    cur["qualification"] = sorted(set(cur["qualification"]) | set(r["qualification"]))
    both = set(cur.get("locations") or []) | set(r.get("locations") or [])
    locs = both - {"All India"}
    if cur.get("level") == "State Govt":
        cur["locations"] = sorted(locs) or ["All India"]
    elif "All India" in both or len(locs) > 2 or not locs:
        # a central notice that aggregators file under several states is an all-India notice
        cur["locations"] = ["All India"]
    else:
        cur["locations"] = sorted(locs)
    ids = set(cur.get("alias_ids", [])) | set(r.get("alias_ids", [])) | {r["id"]}
    ids.discard(cur["id"])
    cur["alias_ids"] = sorted(ids)


def merge(records):
    """Dedupe on id, then fuzzy-merge the same notice across official sites and aggregators."""
    out, alias, by_url = {}, {}, {}
    for r in records:
        if r is None:
            continue
        r.setdefault("source_types", ["aggregator"])
        cur = out.get(r["id"]) or out.get(alias.get(r["id"]))
        if not cur and r["source_types"] == ["aggregator"]:
            cur = out.get(by_url.get(r.get("url")))
        if cur:
            _absorb(cur, r)
        else:
            out[r["id"]] = r
            cur = r
        for a in cur.get("alias_ids", []):
            alias[a] = cur["id"]
        # aggregator article URLs are unique per notice; company pages often reuse one URL
        if r.get("url") and r["source_types"] == ["aggregator"]:
            by_url.setdefault(r["url"], cur["id"])
    items = list(out.values())
    merged = []
    for r in items:
        target = next((m for m in merged if _same_notice(m, r)), None)
        if target:
            _absorb(target, r)
        else:
            merged.append(r)
    # Last pass: a notice seen on one site only, whose organisation has exactly ONE notice with the
    # same last date on another site, is that notice (titles are often worded completely differently:
    # "MECL Non Executive" vs "MECL Technician, Assistant and More").
    final = []
    for r in merged:
        hosts_r = set(r.get("hosts") or [_site(r.get("url"))])
        if len(hosts_r) == 1 and r.get("last_date"):
            cands = [m for m in final if m.get("last_date") == r["last_date"] and _org_match(m, r)
                     and not (hosts_r & set(m.get("hosts") or [_site(m.get("url"))]))
                     and not (m.get("vacancies") and r.get("vacancies") and m["vacancies"] != r["vacancies"])]
            same_org_same_day_here = [m for m in merged if m is not r and m.get("last_date") == r["last_date"]
                                      and _org_match(m, r) and hosts_r & set(m.get("hosts") or [_site(m.get("url"))])]
            if len(cands) == 1 and not same_org_same_day_here:
                _absorb(cands[0], r)
                continue
        final.append(r)
    return final


def is_open(rec, today=None):
    today = today or date.today()
    if rec["last_date"]:
        return date.fromisoformat(rec["last_date"]) >= today
    if not rec.get("posted"):
        return False
    age = (today - date.fromisoformat(rec["posted"])).days
    return age <= (ONGOING_MAX_AGE if rec.get("status") == "Ongoing" else UNDATED_MAX_AGE)


def _doc_link(u):
    """True for a link to one notice's document (an advertisement PDF), not a shared portal or login page."""
    if not u:
        return False
    path = re.sub(r"^https?://[^/]+", "", u).split("?")[0].lower()
    if re.search(r"login|register|registration|frmregistration|allnotifications|examslist|startpage|search|index\.(php|aspx?|html?)$", path):
        return False
    return bool(re.search(r"\.pdf$|/pdf/|advt|advertisement|notification[^s]|detailed", path)) and len(path) > 8


_specific_link = _doc_link  # backwards name


def merge_by_links(jobs):
    """Second dedupe pass once job descriptions are attached.

    Two DIFFERENT sites that point at the same official advertisement PDF are
    listing the same notice, even when their titles, organisation names and
    dates differ. Shared application portals and login pages are ignored: one
    board uses the same portal for many notices.
    """
    owner, out = {}, []
    for j in jobs:
        jd = j.get("jd") or {}
        keys = [l["href"].split("#")[0].rstrip("/").lower() for l in jd.get("links", [])
                if re.search(r"notification|advertisement|advt|notice", l.get("key", ""), re.I) and _doc_link(l["href"])]
        if jd.get("apply_kind") == "notification" and _doc_link(jd.get("apply_url")):
            keys.append(jd["apply_url"].split("#")[0].rstrip("/").lower())
        hosts_j = set(j.get("hosts") or [_site(j.get("url"))])
        target = next((owner[k] for k in keys if k in owner
                       and not (hosts_j & set(owner[k].get("hosts") or [_site(owner[k].get("url"))]))), None)
        if target is not None:
            richer = sum(bool(v) for v in jd.values()) > sum(bool(v) for v in (target.get("jd") or {}).values())
            _absorb(target, j)
            if richer:
                target["jd"] = jd
        else:
            out.append(j)
            target = j
        for k in keys:
            owner.setdefault(k, target)
    return out


# ---------------------------------------------------------------- one job per designation

CATEGORY_ROW = re.compile(r"^(total|grand total|ur|gen(eral)?|obc|sc|st|ews|pwbd|pwd|ph|vh|hh|oh|male|female|women|"
                          r"ex[\s-]?s(m|ervicemen)|category|reserved|unreserved|vacanc(y|ies))\b", re.I)


def _count(v):
    m = re.search(r"\d[\d,]*", str(v if v is not None else ""))
    try:
        return int(m.group().replace(",", "")) if m else None
    except ValueError:
        return None


def _quals(text):
    """Qualification text from a vacancy row -> short display strings.

    Lists of degrees are split ("B.Tech, MBA, CA"); sentences are kept whole
    ("MBBS plus PG degree in Paediatrics") and shortened at a word boundary.
    """
    if not text:
        return []
    text = re.sub(r"\s+", " ", str(text)).strip(" .;")
    parts = [p.strip(" .;") for p in text.split(";")]
    if len(parts) == 1:
        commas = [p.strip() for p in re.split(r",(?![^()]*\))", text)]
        if len(commas) > 1 and all(len(p) <= 25 for p in commas):
            parts = commas

    def short(p, n=80):
        return p if len(p) <= n else p[:n].rsplit(" ", 1)[0].rstrip(",;(") + "…"
    return [short(p) for p in parts if len(p) > 1][:6]


def split_by_post(jobs, max_posts=40):
    """Turn a notice with several designations into one job per designation.

    Uses the vacancy table from the job description ("Post | Posts | Qualification").
    Each post becomes its own job (own page, title, vacancy count and qualification)
    that shares the notice's dates, fee, age limit and Apply link, and lists the
    other posts of the same notice. Category rows (UR/OBC/SC/Total…) are ignored and
    identical post names are added together.
    """
    out = []
    for j in jobs:
        rows = [v for v in (j.get("jd") or {}).get("vacancy") or []
                if v.get("post") and not CATEGORY_ROW.match(str(v["post"]).strip())]
        groups = {}
        for v in rows:
            post = re.sub(r"\s+", " ", str(v["post"])).strip(" -–:")
            key = re.sub(r"[^a-z0-9]", "", post.lower())
            if not key:
                continue
            g = groups.setdefault(key, {"post": post, "count": None, "qual": v.get("qualification"), "rows": []})
            c = _count(v.get("count"))
            if c is not None:
                g["count"] = (g["count"] or 0) + c
            g["qual"] = g["qual"] or v.get("qualification")
            g["rows"].append(v)
        if len(groups) < 2:
            out.append(j)
            continue
        kept = list(groups.items())[:max_posts]
        children = []
        for key, g in kept:
            c = json.loads(json.dumps(j))
            c["id"] = hashlib.sha1(f"{j['id']}|{key}".encode()).hexdigest()[:12]
            c["notice_id"], c["notice_title"] = j["id"], j["title"]
            c["notice_vacancies"] = j.get("vacancies")
            c["title"] = g["post"]
            c["vacancies"] = g["count"]
            c["qualification"] = _quals(g["qual"]) or j.get("qualification", [])
            c["jd"]["vacancy"] = g["rows"]
            if g["qual"]:
                c["jd"]["post_qualification"] = str(g["qual"])
            c.pop("alias_ids", None)
            children.append(c)
        siblings = [{"id": c["id"], "title": c["title"], "vacancies": c["vacancies"]} for c in children]
        for c in children:
            c["siblings"] = [s for s in siblings if s["id"] != c["id"]]
            c["more_posts"] = max(0, len(groups) - max_posts)
        out.extend(children)
    return out
