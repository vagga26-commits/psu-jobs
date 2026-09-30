import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "crawler"))

from normalize import merge, normalize, parse_date, parse_vacancies  # noqa: E402
from orgs import resolve  # noqa: E402
from parsers import parse_official, parse_table  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
TODAY = date(2026, 9, 29)


def test_dates():
    assert parse_date("05-10-2026") == date(2026, 10, 5)
    assert parse_date("28/09/26") == date(2026, 9, 28)
    assert parse_date("Last date: 7th Nov, 2026") == date(2026, 11, 7)
    assert parse_date("") is None


def test_vacancies():
    assert parse_vacancies("Apprentice – 3500 Posts", "") == 3500
    assert parse_vacancies("x", "https://a/b-2026-apply-online-for-58-trade-apprentice-posts-3070008") == 58
    assert parse_vacancies("Manager", "https://a/rites-recruitment-2026-apply-online-for-manager-posts-1") is None


def test_org_resolution():
    assert resolve("Eastern Coalfields")[0] == "ECL"
    assert resolve("SAIL IISCO Steel Plant")[0] == "SAIL"
    assert resolve("Bank of India")[0] == "Bank of India"
    assert resolve("BOI")[0] == "Bank of India"
    assert resolve("Some New PSU Ltd")[3] is False


def test_table_parser_and_filters():
    html = (FIX / "aggregator.html").read_text()
    rows = list(parse_table(html, "https://example.com/psu-jobs/"))
    assert len(rows) == 4
    recs = [normalize(r, "t", only_known=True, today=TODAY) for r in rows]
    kept = [r for r in recs if r]
    # CSIR excluded, unknown private bank dropped by only_known
    assert {r["org"] for r in kept} == {"NTPC", "IOCL"}
    ntpc = next(r for r in kept if r["org"] == "NTPC")
    assert ntpc["last_date"] == "2026-10-05" and ntpc["vacancies"] == 15
    assert ntpc["url"] == "https://example.com/articles/ntpc-assistant-officer-for-15-posts-1"


def test_merge_dedupes_across_sources():
    a = normalize({"org": "NTPC", "title": "Diploma Trainee", "last_date": "03-10-2026", "url": "u1"}, "A")
    b = normalize({"org": "ntpc", "title": "Diploma Trainee – 20 Posts", "last_date": "03/10/2026", "url": "u2"}, "B")
    m = merge([a, b])
    assert len(m) == 1 and m[0]["sources"] == ["A", "B"] and m[0]["vacancies"] == 20


def test_official_parser():
    html = (FIX / "official.html").read_text()
    rows = list(parse_official(html, "https://psu.example.in/careers/", "BEL"))
    titles = [r["title"] for r in rows]
    assert any("Senior Engineer" in t for t in titles)
    assert not any("Result" in t for t in titles)
    se = next(r for r in rows if "Senior Engineer" in r["title"])
    assert parse_date(se["last_date"]) == date(2026, 10, 16)
    assert se["url"].startswith("https://psu.example.in/")


def test_official_status_words():
    html = (FIX / "official.html").read_text()
    rows = list(parse_official(html, "https://psu.example.in/careers/", "POWERGRID"))
    assert not any("Law" in r["title"] for r in rows)          # Closed → skipped
    et = next(r for r in rows if "GATE 2027" in r["title"])
    rec = normalize(et, "POWERGRID careers", today=TODAY, kind="official")
    assert rec["status"] == "Ongoing" and rec["source_types"] == ["official"]
    assert rec["official_url"] == rec["url"]


def test_undated_notices_expire():
    from normalize import is_open
    fresh = normalize({"org": "AAI", "title": "Medical Consultant", "post_date": "28-09-2026"}, "AAI careers", today=TODAY, kind="official")
    stale = normalize({"org": "AAI", "title": "Junior Assistant", "post_date": "04-04-2025"}, "AAI careers", today=TODAY, kind="official")
    nodate = normalize({"org": "IOCL", "title": "Retainer Doctor"}, "IOCL careers", today=TODAY, kind="official")
    assert is_open(fresh, TODAY) and not is_open(stale, TODAY) and not is_open(nodate, TODAY)


def test_cross_source_fuzzy_merge():
    agg = normalize({"org": "AAI", "title": "Quality Manager / Compliance Monitoring Manager",
                     "post_date": "28/09/2026", "last_date": "19-10-2026", "url": "agg"}, "FJA")
    off = normalize({"org": "AAI", "title": "Quality Manager/Compliance Monitoring Manager - Flight Inspection Unit",
                     "post_date": "28-09-2026", "url": "off"}, "AAI careers", kind="official")
    other = normalize({"org": "AAI", "title": "Advisor - Airport Systems", "post_date": "28-09-2026", "url": "x"},
                      "AAI careers", kind="official")
    m = merge([agg, off, other])
    assert len(m) == 2
    q = next(r for r in m if "Quality" in r["title"])
    assert q["source_types"] == ["aggregator", "official"] and q["official_url"] == "off"
    # next run: previous merged record + fresh official row must not split again
    off2 = normalize({"org": "AAI", "title": "Quality Manager/Compliance Monitoring Manager - Flight Inspection Unit",
                      "post_date": "28-09-2026", "url": "off"}, "AAI careers", kind="official")
    assert len(merge([q, off2])) == 1


def test_no_fuzzy_merge_within_same_source_type():
    a = normalize({"org": "SBI", "title": "Specialist Cadre Officers", "last_date": "06-10-2026"}, "SBI careers", kind="official")
    b = normalize({"org": "SBI", "title": "Specialist Cadre Officers (Dean, Faculty)", "last_date": "06-10-2026"}, "SBI careers", kind="official")
    assert len(merge([a, b])) == 2


def test_classify_levels_and_departments():
    from classify import classify
    assert classify("MPESB", "MP Police Constable")[:2] == ("State Govt", "UPSC, SSC & PSC")
    assert classify("Kerala High Court", "Office Attendant")[:2] == ("State Govt", "Judiciary & Legal")
    assert classify("AIIMS Mangalagiri", "Senior Resident")[:2] == ("Central Govt", "Medical & Health")
    assert classify("Canara Bank", "Apprentice")[:2] == ("PSU", "Banking & Finance")
    assert classify("NTPC", "Diploma Trainee")[:2] == ("PSU", "Public Sector Undertakings")
    assert classify("RRB", "NTPC Graduate")[:2] == ("Central Govt", "Railway")
    assert classify("Some Nagar Nigam", "Clerk", hint="Railway")[1] == "Railway"


def test_locations_and_url_dedupe():
    url = "https://www.freejobalert.com/articles/ssc-chsl-1"
    rows = [normalize({"org": "SSC", "title": "CHSL – 2536 Posts", "last_date": "07-10-2026", "url": url, "state": s}, "FJA " + s)
            for s in ("Assam", "Bihar", "Delhi", "Goa")]
    rows.append(normalize({"org": "SSC", "title": "CHSL", "last_date": "07-10-2026", "url": url}, "FJA Govt"))
    m = merge(rows)
    assert len(m) == 1 and m[0]["locations"] == ["All India"]
    st = [normalize({"org": "APPSC", "title": "Group I", "last_date": "27-10-2026", "url": "u", "state": "Andhra Pradesh"}, "FJA AP")]
    assert merge(st)[0]["locations"] == ["Andhra Pradesh"] and merge(st)[0]["level"] == "State Govt"


def test_private_employers_excluded():
    assert normalize({"org": "TMB", "title": "Branch Head", "last_date": "12-10-2026"}, "x") is None
    assert normalize({"org": "Jain University", "title": "Professor", "last_date": "05-10-2026"}, "x") is None


def test_logo_domains():
    from logos import logo_domain
    assert logo_domain("NTPC") == "ntpc.co.in"
    assert logo_domain("AIIMS Mangalagiri") == "aiims.edu"
    assert logo_domain("East Central Railway") == "indianrailways.gov.in"
    assert logo_domain("Koppal District") is None
    rec = normalize({"org": "Canara Bank", "title": "Apprentice", "last_date": "17-10-2026"}, "x")
    assert rec["logo_domain"] == "canarabank.com"


def test_article_parser_and_apply_link():
    from jd import clean_jd
    from parsers.article import parse_article
    raw = parse_article((FIX / "article.html").read_text(), "https://www.freejobalert.com/articles/x")
    assert raw["links"]["apply_online"] == "https://ibpsreg.ibps.in/cabgasep26/"
    assert raw["important_dates"]["Last Date to Apply Online"] == "17-10-2026"
    assert raw["vacancy"][0]["post"] == "Graduate Apprentice"
    assert "Others: Rs. 500" in raw["application_fee"] and raw["how_to_apply"][0].startswith("Register")
    jd = clean_jd(raw)
    assert jd["apply_url"] == "https://ibpsreg.ibps.in/cabgasep26/" and jd["apply_kind"] == "portal"
    assert not any("t.me" in l["href"] for l in jd["links"])


def test_apply_link_fallbacks():
    from jd import clean_jd
    jd = clean_jd({"links": {"apply_online": "mailto:hr@aai.aero", "notification_pdf": "https://aai.aero/a.pdf",
                             "official_website": "https://aai.aero", "x": "https://img2.freejobalert.com/n.pdf"}})
    assert jd["apply_url"] == "https://aai.aero/a.pdf" and jd["apply_kind"] == "notification"
    assert jd["contacts"] == ["hr@aai.aero"]
    assert clean_jd({"links": {"official_website": "https://ssc.gov.in"}})["apply_kind"] == "website"
    assert clean_jd({"error": "timeout"}) is None


def test_seo_site_build(tmp_path):
    import json as _j
    import re as _re
    import sitegen
    root = Path(__file__).resolve().parent.parent
    data = {"generated_at": "2026-09-29T12:00:00+00:00", "count": 2, "sources": [], "jobs": [
        normalize({"org": "Canara Bank", "title": "Apprentice – 3500 Posts", "qualification": "Any Graduate",
                   "post_date": "28/09/2026", "last_date": "17-10-2026", "url": "https://x/a", "state": ""}, "FJA"),
        normalize({"org": "APPSC", "title": "Group I", "qualification": "B.Tech/B.E", "post_date": "15/09/2026",
                   "last_date": "27-10-2026", "url": "https://x/b", "state": "Andhra Pradesh"}, "FJA")]}
    data["jobs"][0]["jd"] = {"apply_url": "https://ibpsreg.ibps.in/x/", "apply_kind": "portal", "links": [], "age_limit": ["20-28 years"]}
    tpl = (root / "web" / "template.html").read_text()
    stats = sitegen.build(data, tpl, "https://jobs.example.in", out=tmp_path)
    assert stats["jobs"] == 2
    pages = list(tmp_path.glob("job/*/index.html"))
    assert len(pages) == 2
    html = next(p for p in pages if "canara" in str(p)).read_text()
    ld = [_j.loads(m) for m in _re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, _re.S)]
    jp = next(x for x in ld if x["@type"] == "JobPosting")
    assert jp["validThrough"].startswith("2026-10-17") and jp["hiringOrganization"]["name"] == "Canara Bank"
    assert jp["totalJobOpenings"] == 3500 and jp["employmentType"] == "INTERN"
    assert '<link rel="canonical" href="https://jobs.example.in/job/' in html
    assert 'href="https://ibpsreg.ibps.in/x/"' in html            # Apply Now → employer
    assert (tmp_path / "andhra-pradesh-govt-jobs" / "index.html").exists()
    assert (tmp_path / "psu-jobs" / "index.html").exists()
    sm = (tmp_path / "sitemap.xml").read_text()
    assert sm.count("<loc>") == stats["urls"] and "https://jobs.example.in/job/" in sm
    home = (tmp_path / "index.html").read_text()
    listed = home.split('<div id="list">', 1)[1].split('id="pager"', 1)[0]
    assert listed.count('class="card tuple"') == 2 and "<h1>" in home   # crawlable without JS


def test_cross_site_dedupe_signals():
    fja = normalize({"org": "SSC", "title": "CHSL – 2536 Posts", "last_date": "07-10-2026",
                     "url": "https://www.freejobalert.com/articles/ssc-chsl"}, "FJA")
    from parsers.links import split_title
    org, post, vac = split_title("SSC CHSL 10+2 Online Form 2026 (2536 Posts)")
    se = normalize({"org": org, "title": f"{post} – {vac} Posts", "last_date": "07-10-2026",
                    "url": "https://www.sarkariexam.com/ssc-chsl-2026/"}, "SarkariExam")
    assert len(merge([fja, se])) == 1
    # deadline extended on one site: same org + same vacancies within 3 weeks -> one job, later date kept
    a = normalize({"org": "Bank of Baroda", "title": "Wealth Executive, Credit Analyst – 1100 Posts", "last_date": "01-10-2026",
                   "url": "https://www.freejobalert.com/articles/bob"}, "FJA")
    b = normalize({"org": "Bank of Baroda", "title": "SO – 1100 Posts", "last_date": "08-10-2026",
                   "url": "https://www.sarkariexam.com/bank-of-baroda-so-2026/"}, "SE")
    m = merge([a, b])
    assert len(m) == 1 and m[0]["last_date"] == "2026-10-08"
    # two different notices from the same site are never fuzzy-merged
    c = normalize({"org": "RITES", "title": "Individual Consultant", "last_date": "11-10-2026", "url": "https://www.freejobalert.com/articles/r1"}, "FJA")
    d = normalize({"org": "RITES", "title": "Individual Consultant", "last_date": "11-10-2026", "url": "https://www.freejobalert.com/articles/r2"}, "FJA")
    assert len(merge([c, d])) == 2
    # different orgs, different counts -> kept apart
    e = normalize({"org": "UPSSSC", "title": "Senior Instructor – 132 Posts", "last_date": "05-10-2026", "url": "https://x.com/1"}, "X")
    f = normalize({"org": "UPSSSC", "title": "Veterinary Pharmacist – 1308 Posts", "last_date": "05-10-2026", "url": "https://y.com/2"}, "Y")
    assert len(merge([e, f])) == 2


def test_merge_by_shared_official_link():
    from normalize import merge_by_links
    j1 = {"id": "1", "org": "MPESB", "title": "MP Police Constable", "sources": ["FJA"], "source_types": ["aggregator"], "qualification": [],
          "url": "https://fja.com/x", "jd": {"apply_url": "https://esb.mp.gov.in/Default.aspx?id=constable", "apply_kind": "portal",
                                        "links": [{"key": "notification_pdf", "href": "https://esb.mp.gov.in/pdf/constable2026.pdf"}]}}
    j2 = {"id": "2", "org": "MP Police", "title": "GD Constable", "sources": ["SE"], "source_types": ["aggregator"], "qualification": [],
          "url": "https://se.com/y", "jd": {"apply_url": "https://esb.mp.gov.in/", "apply_kind": "website",
                                       "links": [{"key": "notification_pdf", "href": "https://esb.mp.gov.in/pdf/constable2026.pdf"}]}}
    out = merge_by_links([j1, j2])
    assert len(out) == 1 and set(out[0]["sources"]) == {"FJA", "SE"}
    assert _specific("https://ssc.gov.in/") is False


def _specific(u):
    from normalize import _specific_link
    return _specific_link(u)


def test_split_title_and_links_parser():
    from parsers.links import parse_links, split_title
    assert split_title("Bihar BTSC Touring Veterinary Officer Online Form 2026") == ("BTSC", "Touring Veterinary Officer", None)
    assert split_title("Bank of India Specialist Officer SO Online Form 2026 – Extend")[0] == "Bank of India"
    assert split_title("BPSC School Teacher TRE 4.0 Online Form 2026 (32,388 Posts) – Start")[2] == 32388
    html = """<html><body><main><ul>
      <li><a href="/ssc-chsl-2026/">SSC CHSL 10+2 Online Form 2026 (2536 Posts)</a> Last Date: 07 October 2026</li>
      <li><a href="/ssc-cgl-result/">SSC CGL Result 2026</a></li>
      <li><a href="https://other.site/x">Other Site Recruitment 2026</a></li></ul></main></body></html>"""
    rows = list(parse_links(html, "https://www.sarkariexam.com/category/top-online-form/"))
    assert len(rows) == 1 and rows[0]["org"] == "SSC" and parse_date(rows[0]["last_date"]) == date(2026, 10, 7)


def test_shared_portal_is_not_a_duplicate_signal():
    from normalize import merge_by_links
    mk = lambda i, t: {"id": i, "org": "RITES", "title": t, "sources": ["FJA"], "source_types": ["aggregator"], "qualification": [],
                       "url": f"https://www.freejobalert.com/articles/{i}", "jd": {"apply_url": "https://recruit.rites.com/frmregistration.aspx",
                       "apply_kind": "portal", "links": [{"key": "apply_online", "href": "https://recruit.rites.com/frmregistration.aspx"}]}}
    assert len(merge_by_links([mk("a", "Assistant Manager"), mk("b", "Individual Consultant")])) == 2


def test_split_notice_into_posts():
    from normalize import split_by_post
    j = normalize({"org": "CONCOR", "title": "Management Trainee & Assistant Officer – 77 Posts", "last_date": "30-09-2026",
                   "url": "https://www.freejobalert.com/articles/concor"}, "FJA")
    j["jd"] = {"apply_url": "https://concor/apply", "apply_kind": "portal", "vacancy": [
        {"post": "Management Trainee - Accounts", "count": "9", "qualification": "Graduate (55% min) + CA"},
        {"post": "Assistant Officer - Civil", "count": 4, "qualification": "B.Tech/B.E, Diploma"},
        {"post": "Assistant Officer - Civil", "count": 2, "qualification": None},     # same post twice -> added up
        {"post": "Total", "count": 77, "qualification": None},                       # category/total rows ignored
        {"post": "UR", "count": 30, "qualification": None}]}
    out = split_by_post([j])
    assert [x["title"] for x in out] == ["Management Trainee - Accounts", "Assistant Officer - Civil"]
    assert [x["vacancies"] for x in out] == [9, 6]
    assert out[1]["qualification"] == ["B.Tech/B.E", "Diploma"]
    assert out[0]["notice_title"].startswith("Management Trainee & Assistant Officer")
    assert out[0]["siblings"][0]["id"] == out[1]["id"] and out[0]["id"] != out[1]["id"]
    assert all(x["jd"]["apply_url"] == "https://concor/apply" for x in out)       # shared Apply link
    single = normalize({"org": "SSC", "title": "CHSL", "last_date": "07-10-2026", "url": "u"}, "X")
    single["jd"] = {"vacancy": [{"post": "LDC/JSA", "count": 2536}]}
    assert split_by_post([single])[0]["title"] == "CHSL"                        # one post: unchanged
