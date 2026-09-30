"""Clean job-description records and pick the original site's link for "Apply Now".

A JD record comes from an aggregator article (see parsers/article.py or the
snapshot files in data/jd/). Aggregator links are never used for Apply Now:
we prefer the employer's application portal, then its official notification,
then its official website.
"""
import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
AGGREGATOR = re.compile(r"freejobalert|sarkariresult|sarkariexam|sarkarinaukriblog|freshersnow|freshersworld|adda247|testbook|jagranjosh|t\.me/|whatsapp|play\.google|instagram|telegram|facebook|youtube", re.I)

APPLY_KEYS = re.compile(r"^(apply_online|apply_online_\d+|application_portal|careers_portal|registration|apply)$", re.I)
NOTICE_KEYS = re.compile(r"notification|advertisement|advt|notice", re.I)
FORM_KEYS = re.compile(r"application_form|apply_offline|form", re.I)
SITE_KEYS = re.compile(r"official_website|website", re.I)

LIST_FIELDS = ("application_fee", "age_limit", "eligibility", "selection_process", "how_to_apply")


def as_text(v):
    """Pages sometimes give pay/fees as a table; flatten to one readable string."""
    if v is None or v == "":
        return None
    if isinstance(v, dict):
        return "; ".join(f"{k.replace('_', ' ')}: {as_text(x)}" for k, x in v.items() if x not in (None, ""))
    if isinstance(v, list):
        return "; ".join(as_text(x) for x in v if x not in (None, ""))
    return str(v)


def _label(key):
    k = key.replace("_", " ").strip()
    k = re.sub(r"\bpdf\b", "PDF", k, flags=re.I)
    return k[:1].upper() + k[1:]


def clean_jd(raw):
    """Return a compact JD dict, or None if the record is empty/errored."""
    if not raw or "error" in raw:
        return None
    links, contacts = [], []
    for key, href in (raw.get("links") or {}).items():
        if not isinstance(href, str):
            continue
        href = href.strip()
        if href.lower().startswith("mailto:"):
            contacts.append(href[7:])
            continue
        if not href.startswith(("http://", "https://")):
            if EMAIL.search(href) and "[email" not in href:
                contacts.append(EMAIL.search(href).group(0))
            elif re.search(r"\d{6,}", href):
                contacts.append(f"{_label(key)}: {href}")
            continue
        if AGGREGATOR.search(href) or href.startswith("blob:"):
            continue
        links.append({"key": key, "label": _label(key), "href": href})

    def first(rx):
        return next((l for l in links if rx.search(l["key"])), None)

    apply = first(APPLY_KEYS) or None
    kind = "portal" if apply else None
    if not apply:
        apply, kind = first(NOTICE_KEYS), "notification"
    if not apply:
        apply, kind = first(FORM_KEYS), "form"
    if not apply:
        apply, kind = first(SITE_KEYS), "website"
    if not apply and links:
        apply, kind = links[0], "website"

    vac = []
    for v in raw.get("vacancy") or []:
        if isinstance(v, dict) and (v.get("post") or v.get("count")):
            vac.append({"post": v.get("post"), "count": v.get("count"), "qualification": v.get("qualification")})

    out = {
        "advt_no": as_text(raw.get("advt_no")),
        "summary": as_text(raw.get("summary")),
        "dates": {k: as_text(v) for k, v in (raw.get("important_dates") or {}).items() if v},
        "pay": as_text(raw.get("pay_scale") or raw.get("remuneration") or raw.get("stipend") or raw.get("honorarium")),
        "vacancy": vac,
        "links": links,
        "contacts": sorted(set(contacts)),
        "apply_url": apply["href"] if apply else None,
        "apply_kind": kind if apply else None,
    }
    for f in LIST_FIELDS:
        vals = raw.get(f) or []
        out[f] = [as_text(x) for x in vals if x] if isinstance(vals, list) else [as_text(vals)]
    return out
