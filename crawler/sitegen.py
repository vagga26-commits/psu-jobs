"""Static, search-engine-friendly site generator.

Builds dist/ as plain HTML pages that crawlers can read without running JS:

  index.html                    search app + pre-rendered latest jobs + link hub
  job/<slug>/index.html         one page per job, JobPosting structured data (Google for Jobs)
  <landing>/index.html          PSU / Central / State, departments, states,
                                qualifications, organisations, closing soon, latest
  sitemap.xml, robots.txt, feed.xml, 404.html, assets/site.css, assets/og.png

Every page has a unique <title>, meta description, canonical URL, Open Graph /
Twitter tags and JSON-LD (JobPosting, BreadcrumbList, ItemList, FAQPage,
WebSite, Organization). Set SITE_URL (e.g. https://jobs.example.in) so
canonical links and the sitemap use your real domain.
"""
import html
import json
import os
import re
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_NAME = "Sarkari Jobs Board"
TODAY = date.fromisoformat(os.environ["TODAY"]) if os.environ.get("TODAY") else date.today()
YEAR = TODAY.year

QUAL = [  # same buckets as the search page
    ("10th / 12th pass", "10th-12th-pass", r"^(5th|7th|8th|10th|12th|intermediate)$|\b(class (8|10|12)|matric(ulation)?|sslc|hsc|10\+2|xth|xiith|10th|12th|intermediate)\b"),
    ("ITI", "iti", r"\biti\b"),
    ("Diploma", "diploma", r"diploma|d\.pharm|dmlt|d\.el\.ed"),
    ("B.Tech / B.E", "btech-be", r"b\.?\s?tech|b\.arch|\bb\.?e\b|engineering degree|degree in engineering"),
    ("Graduate", "graduate", r"graduate|graduation|bachelor|degree|^b\.a$|\bb\.a\b|b\.com|b\.sc|bca|b\.voc|bba|b\.b\.a|bsw|bfsc|b\.lib|bhm"),
    ("Post Graduate / MBA", "post-graduate-mba", r"post graduate|masters|^m\.a$|m\.sc|m\.com|mba|pgdm|mca|msw|m\.lib|m\.p\.ed|mph|^ms$"),
    ("M.Tech / PhD", "mtech-phd", r"m\.e/|m\.tech|m\.phil|ph\.d"),
    ("B.Ed / Teaching", "bed-teaching", r"b\.ed|m\.ed|b\.el\.ed|bped"),
    ("CA / CS / CMA / Law", "ca-cs-law", r"^ca$|^cs$|icwa|icmai|icsi|llb|llm"),
    ("Medical / Nursing / Pharma", "medical-nursing-pharma", r"mbbs|ms/md|dnb|bhms|bams|bums|bds|dental|pharma|gnm|mvsc|bvsc|\bdm\b|m\.ch|bpt|bmlt"),
]
QUAL = [(n, s, re.compile(rx, re.I)) for n, s, rx in QUAL]
LEVEL_SLUG = {"PSU": "psu-jobs", "Central Govt": "central-govt-jobs", "State Govt": "state-govt-jobs"}
e = html.escape


def slugify(s, n=80):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower().replace("&", " and ")).strip("-")
    return s[:n].rstrip("-")


def host(u):
    return re.sub(r"^https?://(www[.])?([^/]+).*", r"\2", u or "")


def posts(n):
    return f"{n:,} Post" if n == 1 else f"{n:,} Posts"


def dnice(d):
    return datetime.fromisoformat(d).strftime("%d %b %Y") if d else ""


def days_left(j):
    return (date.fromisoformat(j["last_date"]) - TODAY).days if j.get("last_date") else None


def quals_of(j):
    return [n for n, _, rx in QUAL if any(rx.search(q) for q in j.get("qualification", []))]


def locs_of(j):
    return j.get("locations") or ["All India"]


# ---------------------------------------------------------------- page text

def job_title_seo(j):
    t = j["title"]
    base = f"{j['org']} {t}" if j["org"].lower() not in t.lower() else t
    vac = f" – {posts(j['vacancies'])}" if j.get("vacancies") else ""
    return f"{base} Recruitment {YEAR}{vac}"


def short_title(t, n=38):
    t = re.sub(r"\s*\([^)]*\)", "", t).strip()
    if len(t) > n:
        cut = re.split(r",|\band more\b|\s&\s|\band\b", t)[0].strip(" -–,")
        t = cut if len(cut) >= 6 else t[:n].rsplit(" ", 1)[0]
    return t


def page_title(j):
    """<title>: keep it near 60 characters so search results don't cut it."""
    st = short_title(j["title"])
    base = st if j["org"].lower() in st.lower() else f"{j['org']} {st}"
    t = f"{base} Recruitment {YEAR}"
    if j.get("vacancies") and len(t) + len(f" – {posts(j['vacancies'])}") <= 60:
        t += f" – {posts(j['vacancies'])}"
    if len(t) + len(" | Sarkari Jobs") <= 70:
        t += " | Sarkari Jobs"
    return t


def job_intro(j):
    """An original, fact-based description paragraph for the job page."""
    jd = j.get("jd") or {}
    org = j.get("org_full") or j["org"]
    parts = [f"{org}{' (' + j['org'] + ')' if j['org'] != org else ''} has announced "
             + (f"{j['vacancies']:,} vacanc{'y' if j['vacancies'] == 1 else 'ies'}" if j.get("vacancies") else "vacancies")
             + f" for {j['title']}."]
    if j.get("notice_title"):
        n = len(j.get("siblings", [])) + 1 + j.get("more_posts", 0)
        parts.append(f"This post is one of {n} in the notice “{j['notice_title']}”.")
    if jd.get("advt_no"):
        parts.append(f"The recruitment is under advertisement {jd['advt_no']}.")
    q = quals_of(j)
    if q:
        parts.append(f"Candidates with {', '.join(q[:3])} qualifications can apply.")
    loc = locs_of(j)
    parts.append("The notice is open to candidates across India." if loc == ["All India"]
                 else f"The posts are in {', '.join(loc)}.")
    if j.get("last_date"):
        mode = f" {j['apply_mode'].lower()}" if j.get("apply_mode") else ""
        parts.append(f"Applications are accepted{mode} until {dnice(j['last_date'])}.")
    if jd.get("pay"):
        parts.append(f"Pay: {jd['pay']}.".replace("..", "."))
    return " ".join(parts)


def job_meta_desc(j):
    bits = [f"{j['org']} {j['title']} {YEAR}"]
    if j.get("vacancies"):
        bits.append(f"{j['vacancies']:,} posts")
    q = quals_of(j)
    if q:
        bits.append(q[0])
    if j.get("last_date"):
        bits.append(f"last date {dnice(j['last_date'])}")
    s = ": ".join([bits[0], ", ".join(bits[1:])]) if len(bits) > 1 else bits[0]
    s += ". Check eligibility, age limit, fee, selection process and apply online on the official site."
    return s[:300]


# ---------------------------------------------------------------- html parts

PALETTE = [("#eef2fe", "#275df5"), ("#e8f6ee", "#1a7d4b"), ("#fdf3e2", "#b25e09"), ("#f6f0fd", "#7a3fbf"),
           ("#fdecec", "#c43d3d"), ("#e6f6f8", "#0f7d8c"), ("#f1f3f7", "#474d6a")]


def hue(s):  # same colour choice as the search page
    h = 0
    for c in s:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return PALETTE[h % len(PALETTE)]


def logo_html(j, cls, rel):
    bg, fg = hue(j["org"])
    sty = f' style="background:{bg};color:{fg}"'
    ini = "".join(w if re.fullmatch(r"[A-Z0-9]{2,6}", w) else w[0] for w in re.sub(r"[^A-Za-z0-9 &]", " ", j["org"]).split())[:4].upper()
    d = j.get("logo_domain")
    if d and (ROOT / "data" / "logos" / f"{d}.png").exists():
        return f'<div class="{cls}"{sty} data-ini="{e(ini)}"><img src="{rel}assets/logos/{e(d)}.png" alt="{e(j["org"])} logo" width="56" height="56" loading="lazy"></div>'
    if d:
        return (f'<div class="{cls}"{sty} data-ini="{e(ini)}"><img src="https://www.google.com/s2/favicons?domain={e(d)}&amp;sz=128" '
                f'alt="{e(j["org"])} logo" width="56" height="56" loading="lazy" referrerpolicy="no-referrer" '
                f'onerror="this.parentElement.textContent=this.parentElement.dataset.ini"></div>')
    return f'<div class="{cls}"{sty} aria-hidden="true">{e(ini)}</div>'


def card_html(j, rel):
    left = days_left(j)
    cls = "" if left is None else "now" if left <= 3 else "soon" if left <= 7 else ""
    due = ("Last date not stated" if left is None else "Closes today" if left == 0 else f"{left} day{'s' if left > 1 else ''} left")
    lv = {"Central Govt": "Central", "State Govt": "State", "PSU": "PSU"}.get(j["level"], "Central")
    q = quals_of(j)
    qs = ", ".join(q[:2]) + (f" +{len(q) - 2}" if len(q) > 2 else "") if q else "See notice"
    tags = "".join(f"<span>{e(x)}</span>" for x in j.get("qualification", [])[:8])
    return f'''<article class="card tuple">
  <h2 class="t-title"><a href="{rel}{j['page']}">{e(j['title'])}</a></h2>
  {logo_html(j, 'logo-t', rel)}
  <div class="t-org"><span class="nm">{e(j['org'])}</span>{f'<span class="full">{e(j["org_full"])}</span>' if j.get('org_full') and j['org_full'] != j['org'] else ''}<span class="badge lv-{lv}">{e(j['level'])}</span></div>
  <div class="meta"><span>{e(qs)}</span><span>{posts(j['vacancies']) if j.get('vacancies') else 'Posts not stated'}</span><span>{e(', '.join(locs_of(j)))}</span></div>
  <div class="desc"><span>{e(j['department'])} · {('Last date ' + dnice(j['last_date'])) if j.get('last_date') else 'Last date not stated'}{(' · Apply ' + j['apply_mode'].lower()) if j.get('apply_mode') else ''}{(' · ' + str(len(j.get('siblings', [])) + 1 + j.get('more_posts', 0)) + ' posts in this notice') if j.get('notice_title') else ''}</span></div>
  {f'<div class="tags">{tags}</div>' if tags else ''}
  <div class="foot"><span class="due {cls}">{due}</span></div>
</article>'''


def head_html(title, desc, canonical, rel, jsonld=(), og_type="website", robots="index,follow"):
    ld = "".join('<script type="application/ld+json">' + json.dumps(x, ensure_ascii=False).replace("</", "<\\/") + "</script>\n" for x in jsonld)
    return f'''<!doctype html>
<html lang="en-IN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta name="robots" content="{robots},max-image-preview:large,max-snippet:-1">
<link rel="canonical" href="{e(canonical)}">
<meta property="og:site_name" content="{SITE_NAME}"><meta property="og:type" content="{og_type}">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(canonical)}"><meta property="og:image" content="{e(BASE)}/assets/og.png">
<meta property="og:locale" content="en_IN">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{e(title)}"><meta name="twitter:description" content="{e(desc)}">
<meta name="theme-color" content="#275df5">
<link rel="icon" href="{rel}assets/favicon.svg" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="{SITE_NAME} – latest jobs" href="{rel}feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
<link rel="stylesheet" href="{rel}assets/site.css">
{ld}</head>'''


def header_html(rel, on="jobs"):
    def a(key, href, label):
        return f'<a href="{rel}{href}"{" class=on" if key == on else ""}>{label}</a>'
    return f'''<body>
<header class="hdr"><div class="hdr-in">
  <a class="logo" href="{rel or './'}" aria-label="{SITE_NAME} home">sarkari<span>jobs board</span></a>
  <nav class="nav" aria-label="Main">{a("jobs", "", "Jobs")}{a("psu", "psu-jobs/", "PSU")}{a("central", "central-govt-jobs/", "Central Govt")}{a("state", "state-govt-jobs/", "State Govt")}</nav>
  <div class="hdr-right"><a class="btn-f" href="{rel}closing-soon/">Closing this week</a></div>
</div></header>'''


def search_form(rel, q=""):
    return f'''<form class="search-band" action="{rel or './'}" method="get" role="search"><div class="pill">
  <label class="f"><input name="q" type="search" value="{e(q)}" placeholder="Enter post / organisation / exam (e.g. apprentice, NTPC, SSC)" aria-label="Keyword"></label>
  <label class="f"><input name="loc" placeholder="Enter state" aria-label="State"></label>
  <button class="go" type="submit">Search</button></div></form>'''


def crumbs_html(items, rel):
    out = []
    for i, (label, href) in enumerate(items):
        out.append(f'<a href="{rel}{href}">{e(label)}</a>' if href is not None and i < len(items) - 1 else f"<span>{e(label)}</span>")
    return '<nav class="crumbs" aria-label="Breadcrumb">' + '<span aria-hidden="true">›</span>'.join(out) + "</nav>"


def crumbs_ld(items):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": label, **({"item": f"{BASE}/{href}"} if href is not None else {})}
        for i, (label, href) in enumerate(items)]}


def footer_html(rel):
    return f'<footer>{HUB.replace("{rel}", rel)}<p class="disclaimer">Always check eligibility, age limit and fee in the official advertisement before applying. Job details are compiled from the recruiting organisation\'s notice and public job portals.</p></footer>\n</body></html>\n'


# ---------------------------------------------------------------- JSON-LD

def jobposting_ld(j, url):
    jd = j.get("jd") or {}
    desc = f"<p>{e(job_intro(j))}</p>"
    for label, key in (("Eligibility", "eligibility"), ("Age limit", "age_limit"), ("Application fee", "application_fee"),
                       ("Selection process", "selection_process"), ("How to apply", "how_to_apply")):
        if jd.get(key):
            desc += f"<h3>{label}</h3><ul>" + "".join(f"<li>{e(x)}</li>" for x in jd[key]) + "</ul>"
    locs = locs_of(j)
    place = [{"@type": "Place", "address": {"@type": "PostalAddress", "addressCountry": "IN",
                                            **({"addressRegion": l} if l != "All India" else {})}} for l in locs]
    org = {"@type": "Organization", "name": j.get("org_full") or j["org"]}
    site = next((l["href"] for l in jd.get("links", []) if "official_website" in l["key"]), None)
    if site:
        org["sameAs"] = site
    if j.get("logo_domain"):
        org["logo"] = f"{BASE}/assets/logos/{j['logo_domain']}.png" if (ROOT / "data" / "logos" / f"{j['logo_domain']}.png").exists() else None
        if not org["logo"]:
            del org["logo"]
    ld = {"@context": "https://schema.org/", "@type": "JobPosting", "title": j["title"], "description": desc,
          "datePosted": j.get("posted") or j.get("first_seen") or TODAY.isoformat(),
          "hiringOrganization": org, "jobLocation": place, "url": url, "directApply": False,
          "industry": j.get("sector") or j["department"], "occupationalCategory": j["department"]}
    if j.get("last_date"):
        ld["validThrough"] = f"{j['last_date']}T23:59:59+05:30"
    if j.get("vacancies"):
        ld["totalJobOpenings"] = j["vacancies"]
    if jd.get("advt_no"):
        ld["identifier"] = {"@type": "PropertyValue", "name": org["name"], "value": jd["advt_no"]}
    t = j["title"].lower()
    if re.search(r"apprentice|intern", t):
        ld["employmentType"] = "INTERN"
    elif re.search(r"contract|consultant|young professional|fellow|project", t):
        ld["employmentType"] = "CONTRACTOR"
    if j.get("qualification"):
        ld["educationRequirements"] = ", ".join(j["qualification"])
    return ld


def faq_items(j):
    jd = j.get("jd") or {}
    items = []
    if j.get("last_date"):
        items.append((f"What is the last date to apply for {j['org']} {j['title']}?",
                      f"The last date is {dnice(j['last_date'])}."))
    if j.get("vacancies"):
        items.append((f"How many vacancies are there in {j['org']} {j['title']} {YEAR}?", f"There are {j['vacancies']:,} posts."))
    if j.get("qualification"):
        items.append(("What qualification is required?", ", ".join(j["qualification"]) + ". Check the official notification for exact criteria."))
    if jd.get("age_limit"):
        items.append(("What is the age limit?", " ".join(jd["age_limit"][:3])))
    if jd.get("application_fee"):
        items.append(("What is the application fee?", " ".join(jd["application_fee"][:3])))
    if jd.get("apply_url"):
        items.append((f"How do I apply for {j['org']} {j['title']}?",
                      "Use the Apply Now button on this page. It opens the organisation's official "
                      + {"portal": "application portal", "notification": "notification", "form": "application form"}.get(jd.get("apply_kind"), "website") + "."))
    return items


# ---------------------------------------------------------------- pages

def write(path, text):
    p = DIST / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def job_page(j, all_jobs):
    rel, url = "../../", f"{BASE}/{j['page']}"
    jd = j.get("jd") or {}
    apply = jd.get("apply_url") or j.get("official_url")
    title = j.get("_title") or page_title(j)
    lvl = j["level"]
    trail = [("Home", ""), (f"{lvl} Jobs", LEVEL_SLUG[lvl] + "/")]
    if j["org"] in ORG_PAGES:
        trail.append((f"{j['org']} Recruitment", ORG_PAGES[j["org"]]))
    trail.append((j["title"], None))
    faqs = faq_items(j)
    ld = [jobposting_ld(j, url), crumbs_ld(trail)]
    if faqs:
        ld.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]})
    left = days_left(j)
    note = {"portal": "Opens the official application portal", "notification": "Opens the official notification",
            "form": "Opens the official application form", "website": "Opens the organisation's official website",
            "company page": "Opens the notice on the organisation's website"}.get(jd.get("apply_kind"), "Opens the original site")
    apply_host = host(apply)

    def lst(label, key, ordered=False):
        v = jd.get(key) or []
        tag = "ol" if ordered else "ul"
        return f"<h3>{label}</h3><{tag}>" + "".join(f"<li>{e(x)}</li>" for x in v) + f"</{tag}>" if v else ""

    dates = "".join(f"<tr><td>{e(k.replace('_', ' ').capitalize())}</td><td class=n>{e(str(v))}</td></tr>" for k, v in (jd.get("dates") or {}).items())
    vac = "".join(f"<tr><td>{e(str(v.get('post') or ''))}</td><td class=n>{e(str(v.get('count') or ''))}</td><td>{e(str(v.get('qualification') or ''))}</td></tr>" for v in jd.get("vacancy") or [])
    links = "".join(f'<a href="{e(l["href"])}" target="_blank" rel="noopener nofollow">{e(l["label"])} <small>{e(host(l["href"]))}</small></a>' for l in jd.get("links") or [])
    sib_ids = {x["id"] for x in j.get("siblings", [])}
    similar = [x for x in all_jobs if x["id"] != j["id"] and x["id"] not in sib_ids and (x["org"] == j["org"] or x["department"] == j["department"])]
    similar.sort(key=lambda x: (x["org"] != j["org"], days_left(x) if days_left(x) is not None else 999))
    sim = "".join(f'<a class="row" href="{rel}{x["page"]}"><span><span class="tt">{e(x["title"])}</span><span class="ss">{e(x["org"])} · {e(", ".join(locs_of(x)))}</span><span class="ss">{("Last date " + dnice(x["last_date"])) if x.get("last_date") else ""}</span></span>{logo_html(x, "logo-t", rel)}</a>' for x in similar[:8])
    src = []
    if "aggregator" in j.get("source_types", []) and j.get("url"):
        src.append(f'<a href="{e(j["url"])}" target="_blank" rel="noopener nofollow">{e(host(j["url"]))}</a>')
    if j.get("official_url"):
        src.append(f'<a href="{e(j["official_url"])}" target="_blank" rel="noopener">{e(host(j["official_url"]))}</a>')
    others = ""
    if j.get("siblings"):
        by_id = {x["id"]: x for x in all_jobs}
        rows = "".join(f'<a class="row" href="{rel}{by_id[s_["id"]]["page"]}"><span><span class="tt">{e(s_["title"])}</span>'
                       f'<span class="ss">{posts(s_["vacancies"]) if s_.get("vacancies") else "Posts not stated"}</span></span></a>'
                       for s_ in j["siblings"] if s_["id"] in by_id)
        more = f'<p class="small" style="margin-top:10px">…and {j["more_posts"]} more posts – see the official notification.</p>' if j.get("more_posts") else ""
        others = (f'<section class="card jd-card sim"><h2>Other posts in this notice</h2>'
                  f'<p class="small" style="margin:0 0 6px">{e(j["notice_title"])}{(" · " + posts(j["notice_vacancies"]) + " in total") if j.get("notice_vacancies") else ""}</p>{rows}{more}</section>')
    body = f'''{header_html(rel, {"PSU": "psu", "Central Govt": "central", "State Govt": "state"}[lvl])}
{crumbs_html(trail, rel)}
<main class="jdpage"><div>
  <section class="card jd-top">
    <h1>{e(job_title_seo(j))}</h1>
    {logo_html(j, 'logo-t', rel)}
    <div class="t-org"><span class="nm">{e(j['org'])}</span>{f'<span class="full">{e(j["org_full"])}</span>' if j.get('org_full') and j['org_full'] != j['org'] else ''}<span class="badge lv-{ {"Central Govt": "Central", "State Govt": "State", "PSU": "PSU"}[lvl] }">{e(lvl)}</span></div>
    <div class="meta"><span>{e(", ".join(quals_of(j)) or "See notice")}</span><span>{posts(j['vacancies']) if j.get('vacancies') else 'Posts not stated'}</span><span>{e(", ".join(locs_of(j)))}</span>{f'<span>{e(jd["pay"][:70])}</span>' if jd.get('pay') else ''}</div>
    <div class="jd-bar">
      <div class="jd-stats"><span>Posted: <b>{dnice(j.get('posted')) or '—'}</b></span><span>Last date: <b>{dnice(j.get('last_date')) or 'Not stated'}</b></span><span>Status: <b>{'Not stated' if left is None else 'Closes today' if left == 0 else f'{left} days left'}</b></span>{f"<span>Mode: <b>{e(j['apply_mode'])}</b></span>" if j.get('apply_mode') else ''}</div>
      <div class="jd-actions">{f'<a class="apply" href="{e(apply)}" target="_blank" rel="noopener">Apply Now</a><span class="apply-note">{note} · {e(apply_host)}</span>' if apply else ''}</div>
    </div>
  </section>
  <section class="card jd-card">
    <h2>Job description</h2>
    <p>{e(job_intro(j))}</p>
    {f'<p style="margin-top:10px">{e(jd["summary"])}</p>' if jd.get('summary') else ''}
    <h3>Key details</h3><dl class="kv">
      {f'<dt>Advertisement</dt><dd>{e(jd["advt_no"])}</dd>' if jd.get('advt_no') else ''}
      <dt>Organisation</dt><dd>{e(j.get('org_full') or j['org'])}</dd><dt>Job type</dt><dd>{e(lvl)}</dd>
      <dt>Department</dt><dd>{e(j['department'])}</dd><dt>Location</dt><dd>{e(", ".join(locs_of(j)))}</dd>
      {f'<dt>Pay / stipend</dt><dd>{e(jd["pay"])}</dd>' if jd.get('pay') else ''}</dl>
    {f'<h3>Important dates</h3><div class="tbl-wrap"><table class="tbl"><tbody>{dates}</tbody></table></div>' if dates else ''}
    {f'<h3>Vacancy details</h3><div class="tbl-wrap"><table class="tbl"><thead><tr><th>Post</th><th>Posts</th><th>Qualification</th></tr></thead><tbody>{vac}</tbody></table></div>' if vac else ''}
    {lst('Eligibility', 'eligibility')}{lst('Age limit', 'age_limit')}{lst('Application fee', 'application_fee')}
    {lst('Selection process', 'selection_process')}{lst('How to apply', 'how_to_apply', True)}
    {'<h3>Education</h3><div class="skills">' + "".join(f"<span>{e(q)}</span>" for q in j.get("qualification", [])) + '</div>' if j.get('qualification') else ''}
    {f'<h3>Official links</h3><div class="olinks">{links}</div>' if links else ''}
    {'<h3>Contact</h3><ul>' + "".join(f"<li>{e(c)}</li>" for c in jd["contacts"]) + '</ul>' if jd.get('contacts') else ''}
    <p class="srcnote">Sources: {' and '.join(src) or "the organisation's website"}. Check the official notification before you apply.</p>
  </section>
  {others}
  {'<section class="card jd-card"><h2>Frequently asked questions</h2><div class="faq">' + "".join(f"<div><h3>{e(q)}</h3><p>{e(a)}</p></div>" for q, a in faqs) + '</div></section>' if faqs else ''}
  <section class="card jd-card"><h2>About {e(j.get('org_full') or j['org'])}</h2>
    <p>{e(j.get('org_full') or j['org'])} · {e(lvl)} · {e(j['department'])}{(' · ' + e(j['sector'])) if j.get('sector') else ''}</p>
    {f'<p style="margin-top:8px"><a href="{rel}{ORG_PAGES[j["org"]]}">All {e(j["org"])} recruitment notices</a></p>' if j['org'] in ORG_PAGES else ''}
  </section>
</div>
<aside class="card sim" aria-label="Similar jobs"><h2>Jobs you might be interested in</h2>{sim or '<p class="small">No similar jobs right now.</p>'}</aside>
</main>'''
    desc = job_meta_desc(j)
    write(f"{j['page']}index.html", head_html(title, desc, url, rel, ld, og_type="article") + body + footer_html(rel))


def landing_page(slug, h1, intro, jobs, crumb_label, extra=None, meta=None):
    rel, url = "../", f"{BASE}/{slug}/"
    jobs = sorted(jobs, key=lambda j: (j.get("posted") or "") , reverse=True)
    trail = [("Home", ""), (crumb_label, None)]
    ld = [crumbs_ld(trail), {"@context": "https://schema.org", "@type": "ItemList", "numberOfItems": len(jobs),
                             "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": f"{BASE}/{j['page']}"} for i, j in enumerate(jobs[:100])]}]
    extra_html = ""
    if extra:
        t, ex_jobs = extra
        extra_html = f'<h2 class="sec">{e(t)}</h2>' + "".join(card_html(j, rel) for j in ex_jobs)
    top_orgs = sorted({j["org"] for j in jobs}, key=lambda o: -sum(1 for j in jobs if j["org"] == o))[:10]
    closing = sorted([j for j in jobs if days_left(j) is not None and days_left(j) <= 7], key=days_left)[:8]
    side = (f'<aside class="rail" style="display:grid"><div class="card"><h2>Closing soon</h2><div class="rl">'
            + ("".join(f'<a href="{rel}{j["page"]}" style="grid-template-columns:minmax(0,1fr)"><span><span class="tt">{e(j["title"])}</span><span class="ss">{e(j["org"])} · <b>{"today" if days_left(j) == 0 else str(days_left(j)) + "d left"}</b></span></span></a>' for j in closing) or '<p class="small">Nothing closes this week.</p>')
            + '</div></div><div class="card"><h2>Top organisations</h2><div class="orgs">'
            + "".join(f'<a class="chip" href="{rel}{ORG_PAGES[o]}">{e(o)}</a>' if o in ORG_PAGES else f'<span class="chip">{e(o)}</span>' for o in top_orgs)
            + "</div></div></aside>")
    total = sum(j.get("vacancies") or 0 for j in jobs)
    body = f'''{header_html(rel)}
{crumbs_html(trail, rel)}
<section class="intro"><h1>{e(h1)}</h1><p>{e(intro)}</p></section>
{search_form(rel)}
<main class="lp"><section aria-label="Jobs">
  <p class="count" style="margin:4px 0 14px;color:var(--ink2)"><b>{len(jobs)}</b> open notice{'s' if len(jobs) != 1 else ''}{f' · {total:,} declared posts' if total else ''} · updated {dnice(TODAY.isoformat())}</p>
  {"".join(card_html(j, rel) for j in jobs) or '<div class="card empty"><b>No open notices right now</b>New notices appear here as soon as they are published.</div>'}
  {extra_html}
</section>{side}</main>'''
    desc = meta or f"{h1}. {intro}"[:300]
    write(f"{slug}/index.html", head_html(f"{h1} | Sarkari Jobs" if len(h1) <= 55 else h1, desc, url, rel, ld) + body + footer_html(rel))
    return slug


# ---------------------------------------------------------------- build

def build(data, template_html, base_url, out=None):
    global BASE, DIST, HUB, ORG_PAGES
    BASE = base_url.rstrip("/")
    DIST = Path(out) if out else ROOT / "dist"
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "assets").mkdir(parents=True)
    # drop notices whose last date has passed since the crawl (their pages disappear → 404)
    jobs = data["jobs"] = [j for j in data["jobs"] if days_left(j) is None or days_left(j) >= 0]
    for j in jobs:
        j["page"] = f"job/{slugify(job_title_seo(j), 90)}-{j['id'][:6]}/"

    # --- landing page definitions
    pages = []  # (slug, h1, intro, jobs, crumb, extra, group, link label)
    by = lambda f: [j for j in jobs if f(j)]
    for lvl, slug in LEVEL_SLUG.items():
        lj = by(lambda j, l=lvl: j["level"] == l)
        label = {"PSU": "PSU Jobs", "Central Govt": "Central Govt Jobs", "State Govt": "State Govt Jobs"}[lvl]
        pages.append((slug, f"{label} {YEAR} – {len(lj)} Latest Vacancies",
                      f"All open {label.lower()} notices in India: {len(lj)} recruitments from {len({j['org'] for j in lj})} organisations. "
                      "Check the last date, qualification and posts, then apply on the official website.", lj, label, None, "Job type", label))
    depts = sorted({j["department"] for j in jobs})
    for d in depts:
        dj = by(lambda j, d=d: j["department"] == d)
        slug = slugify(d) + "-jobs"
        pages.append((slug, f"{d} Jobs {YEAR} – {len(dj)} Govt Vacancies",
                      f"Latest government {d.lower()} jobs across India with last dates, eligibility and official apply links.", dj, f"{d} Jobs", None, "Departments", f"{d} Jobs"))
    states = sorted({l for j in jobs for l in locs_of(j) if l != "All India"})
    all_india = sorted(by(lambda j: locs_of(j) == ["All India"]), key=lambda j: days_left(j) if days_left(j) is not None else 999)
    for s in states:
        sj = by(lambda j, s=s: s in locs_of(j))
        pages.append((slugify(s) + "-govt-jobs", f"{s} Govt Jobs {YEAR} – {len(sj)} Latest Vacancies",
                      f"Government jobs in {s}: state government, district, PSC and central-government posts located in {s}, "
                      f"plus all-India notices open to candidates from {s}.", sj, f"{s} Govt Jobs",
                      (f"All-India notices open to candidates from {s}", all_india[:30]), "States", f"{s} Govt Jobs"))
    for name, slug, rx in QUAL:
        qj = by(lambda j, n=name: n in quals_of(j))
        if qj:
            pages.append((f"{slug}-govt-jobs", f"{name} Govt Jobs {YEAR} – {len(qj)} Vacancies",
                          f"Government, PSU and state jobs for {name} candidates, with last dates and official apply links.", qj,
                          f"{name} Govt Jobs", None, "Qualification", f"{name} Govt Jobs"))
    org_count = {}
    for j in jobs:
        org_count[j["org"]] = org_count.get(j["org"], 0) + 1
    ORG_PAGES = {}
    for o, n in sorted(org_count.items(), key=lambda x: -x[1]):
        if n >= 2:
            ORG_PAGES[o] = f"{slugify(o)}-recruitment/"
    for o in ORG_PAGES:
        oj = by(lambda j, o=o: j["org"] == o)
        full = oj[0].get("org_full") or o
        pages.append((ORG_PAGES[o].rstrip("/"), f"{o} Recruitment {YEAR} – {len(oj)} Openings",
                      f"Latest {full} recruitment notices: {', '.join(sorted({j['title'] for j in oj})[:4])}. See last dates and apply on the official site.",
                      oj, f"{o} Recruitment", None, "Organisations", f"{o} Recruitment"))
    cs = by(lambda j: days_left(j) is not None and days_left(j) <= 7)
    pages.append(("closing-soon", f"Govt Jobs Closing This Week – {len(cs)} Last-Date Alerts",
                  "Government job applications that close in the next 7 days. Apply before the last date.", cs, "Closing this week", None, "Popular", "Closing this week"))
    lt = by(lambda j: j.get("posted") and (TODAY - date.fromisoformat(j["posted"])).days <= 7)
    pages.append(("latest-govt-jobs", f"Latest Govt Jobs {YEAR} – {len(lt)} New Notices This Week",
                  "Government, PSU and state job notifications published in the last 7 days.", lt, "Latest govt jobs", None, "Popular", "Latest govt jobs"))
    wi = by(lambda j: j.get("apply_mode") == "Walk-in")
    if wi:
        pages.append(("walk-in-interview-govt-jobs", f"Walk-in Interview Govt Jobs {YEAR} – {len(wi)} Openings",
                      "Government walk-in interviews: no online application, attend on the given date with documents.", wi, "Walk-in interviews", None, "Popular", "Walk-in interviews"))

    # --- link hub (footer on every page)
    groups = {}
    for p in pages:
        groups.setdefault(p[6], []).append(p)
    order = ["Popular", "Job type", "Departments", "Qualification", "States", "Organisations"]
    hub = '<div class="hub">'
    for g in order:
        items = groups.get(g, [])
        if g in ("States", "Organisations"):
            items = sorted(items, key=lambda p: -len(p[3]))[:16]
        hub += f"<div><h2>{g}</h2><ul>" + "".join(f'<li><a href="{{rel}}{p[0]}/">{e(p[7])}</a></li>' for p in items) + "</ul></div>"
    HUB = hub + "</div>"

    # --- write pages
    seen = {}
    for j in jobs:
        seen.setdefault(page_title(j), []).append(j)
    for t, group in seen.items():
        for j in group:
            j["_title"] = t if len(group) == 1 or not j.get("last_date") else re.sub(r"( \| Sarkari Jobs)?$", "", t) + f" – Last Date {datetime.fromisoformat(j['last_date']).strftime('%d %b')}"
    for j in jobs:
        job_page(j, jobs)
    for p in pages:
        landing_page(p[0], p[1], p[2], p[3], p[4], p[5])

    # --- home: interactive app + pre-rendered list + intro + hub
    # the home page only needs what the list, filters and cards show (job pages carry the rest)
    KEEP = ("id", "org", "org_full", "title", "level", "department", "sector", "locations", "vacancies", "apply_mode",
            "posted", "last_date", "status", "source_types", "page", "logo_domain", "notice_title", "url", "official_url")
    lite = {"generated_at": data.get("generated_at"), "count": len(jobs), "sources": data.get("sources", []),
            "jobs": [{**{k: j[k] for k in KEEP if j.get(k) not in (None, "", [])},
                      "qualification": j.get("qualification", [])[:4],
                      **({"siblings": [0] * len(j["siblings"])} if j.get("siblings") else {})} for j in jobs],
            "site": {"root": "", "base": BASE}}
    (DIST / "assets").mkdir(parents=True, exist_ok=True)
    (DIST / "assets" / "jobs.json").write_text(json.dumps(lite, ensure_ascii=False, separators=(",", ":")))
    blob = json.dumps({"src": "assets/jobs.json", "site": lite["site"]})
    latest = sorted(jobs, key=lambda j: j.get("posted") or "", reverse=True)[:20]
    total = sum(j.get("vacancies") or 0 for j in jobs)
    app = (template_html.replace("/*__DATA__*/", blob)
           .replace("<!--SEO_LIST-->", "".join(card_html(j, "") for j in latest))
           .replace("<!--SEO_INTRO-->", f'<section class="intro"><h1>Sarkari Jobs {YEAR}: Latest Govt, PSU &amp; State Govt Jobs</h1>'
                    f'<p>{len(jobs)} open government job notices from {len({j["org"] for j in jobs})} organisations with {total:,} declared posts. '
                    'Filter by state, department and qualification, then apply on the official website.</p></section>')
           .replace("<!--SEO_LINKS-->", HUB.replace("{rel}", ""))
           .replace("/*HOME*/", "./").replace("/*NAV_PSU*/", "psu-jobs/").replace("/*NAV_CENTRAL*/", "central-govt-jobs/")
           .replace("/*NAV_STATE*/", "state-govt-jobs/"))
    app = re.sub(r"^<title>.*?</title>\n", "", app, flags=re.S)
    css, _, rest = app.partition("</style>")
    css_head = css.split("<style>", 1)
    home_ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": SITE_NAME, "url": BASE + "/"},
               {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": [
                   {"@type": "ListItem", "position": i + 1, "url": f"{BASE}/{j['page']}"} for i, j in enumerate(latest)]}]
    head = head_html(f"Sarkari Jobs {YEAR} – Latest Govt, PSU & State Govt Jobs",
                     f"{len(jobs)} latest government jobs in India: PSU, central and state govt, railway, bank, defence, teaching and "
                     "police vacancies with last dates, eligibility and official apply links. Updated daily.", BASE + "/", "", home_ld)
    (DIST / "assets" / "site.css").write_text(css_head[1])
    head = head.replace("</head>", "")
    write("index.html", head + css_head[0].replace('<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n', "").replace('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">\n', "") + "</head>\n<body>" + rest + "\n</body></html>\n")

    # --- assets, sitemap, robots, feed, 404
    logos = ROOT / "data" / "logos"
    if logos.exists():
        shutil.copytree(logos, DIST / "assets" / "logos", ignore=shutil.ignore_patterns(".gitkeep"))
    (DIST / "assets" / "favicon.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#275df5"/><text x="32" y="44" font-family="Arial,sans-serif" font-size="34" font-weight="700" fill="#fff" text-anchor="middle">S</text></svg>')
    og_image(DIST / "assets" / "og.png", len(jobs))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = [(BASE + "/", now, "hourly", "1.0")] + [(f"{BASE}/{p[0]}/", now, "daily", "0.8") for p in pages] + \
           [(f"{BASE}/{j['page']}", j.get("posted") or now, "daily", "0.7") for j in jobs]
    (DIST / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                      + "".join(f"<url><loc>{e(u)}</loc><lastmod>{m}</lastmod><changefreq>{c}</changefreq><priority>{p}</priority></url>\n" for u, m, c, p in urls)
                                      + "</urlset>\n")
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nDisallow: /offline/\n\nSitemap: {BASE}/sitemap.xml\n")
    feed = sorted(jobs, key=lambda j: j.get("posted") or "", reverse=True)[:50]
    (DIST / "feed.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
                                   f"<title>{SITE_NAME} – latest government jobs</title><link>{e(BASE)}/</link><description>Latest government, PSU and state jobs in India</description><language>en-in</language>"
                                   + "".join(f"<item><title>{e(job_title_seo(j))}</title><link>{e(BASE)}/{j['page']}</link><guid>{e(BASE)}/{j['page']}</guid>"
                                             f"<description>{e(job_meta_desc(j))}</description>"
                                             + (f"<pubDate>{datetime.fromisoformat(j['posted']).strftime('%a, %d %b %Y 00:00:00 +0530')}</pubDate>" if j.get("posted") else "")
                                             + "</item>" for j in feed) + "</channel></rss>\n")
    nf = head_html(f"Page not found | {SITE_NAME}", "This job notice has closed or moved. Search current government jobs.", BASE + "/404.html", "/", robots="noindex,follow")
    (DIST / "404.html").write_text(nf.replace('href="/assets', f'href="{BASE}/assets') + header_html(BASE + "/") +
                                   '<section class="intro"><h1>This page isn\'t available</h1><p>The notice may have closed after its last date. Search the latest government jobs instead.</p></section>'
                                   + search_form(BASE + "/") + footer_html(BASE + "/"))
    (DIST / ".nojekyll").write_text("")
    return {"jobs": len(jobs), "landing": len(pages), "urls": len(urls)}


def og_image(path, n):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return
    im = Image.new("RGB", (1200, 630), (39, 93, 245))
    d = ImageDraw.Draw(im)
    def font(size):
        for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"):
            try:
                return ImageFont.truetype(f, size)
            except OSError:
                continue
        return ImageFont.load_default()
    d.text((80, 170), "Sarkari Jobs Board", font=font(78), fill="white")
    d.text((80, 290), f"{n} open government, PSU & state jobs", font=font(40), fill=(226, 234, 255))
    d.text((80, 350), "Last dates · eligibility · official apply links", font=font(34), fill=(226, 234, 255))
    im.save(path)
