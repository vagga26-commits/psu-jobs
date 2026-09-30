#!/usr/bin/env python3
"""Build the website into dist/.

  dist/                      SEO multi-page site (see crawler/sitegen.py) – deploy this
  dist/offline/sarkari-jobs-board.html
                             single self-contained file (all jobs + descriptions), opens from disk

Set SITE_URL to your live address (e.g. https://jobs.example.in) so canonical
links, the sitemap and structured data use it.
"""
import base64
import re
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import sitegen  # noqa: E402
from jd import as_text  # noqa: E402
from normalize import merge_by_links, split_by_post  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def load():
    data = json.loads((ROOT / "data" / "jobs.json").read_text())
    jd_path = ROOT / "data" / "jd.json"
    jds = json.loads(jd_path.read_text()) if jd_path.exists() else {}
    with_jd = 0
    for j in data["jobs"]:
        jd = jds.get(j.get("url"))
        if jd:
            j["jd"] = dict(jd)
            for k in ("pay", "advt_no", "summary"):
                j["jd"][k] = as_text(jd.get(k))
            for k in ("eligibility", "age_limit", "application_fee", "selection_process", "how_to_apply"):
                j["jd"][k] = [as_text(x) for x in jd.get(k) or [] if x]
            j["jd"]["dates"] = {k: as_text(v) for k, v in (jd.get("dates") or {}).items() if v}
            # link-list sources carry no qualification column: take it from the vacancy table
            if not j.get("qualification"):
                q = {x.strip() for v in jd.get("vacancy") or [] for x in re.split(r",|/| or ", str(v.get("qualification") or "")) if 1 < len(x.strip()) <= 40}
                j["qualification"] = sorted(q)[:8]
            if not j.get("vacancies"):
                try:
                    j["vacancies"] = sum(int(str(v.get("count")).replace(",", "")) for v in jd.get("vacancy") or []) or None
                except (TypeError, ValueError):
                    pass
            with_jd += 1
        # company-site notices link to the employer directly
        if j.get("official_url") and not (jd and jd.get("apply_kind") == "portal"):
            j.setdefault("jd", {})
            j["jd"]["apply_url"] = j["official_url"]
            j["jd"]["apply_kind"] = "company page"
    before = len(data["jobs"])
    data["jobs"] = merge_by_links(data["jobs"])
    data["count"] = len(data["jobs"])
    data["deduped_by_link"] = before - len(data["jobs"])
    notices = len(data["jobs"])
    data["jobs"] = split_by_post(data["jobs"])      # one job per designation
    data["count"] = len(data["jobs"])
    data["notices"] = notices
    return data, with_jd


def main():
    base = os.environ.get("SITE_URL") or "https://example.github.io/sarkari-jobs"
    data, with_jd = load()
    template = (ROOT / "web" / "template.html").read_text()
    stats = sitegen.build(json.loads(json.dumps(data)), template, base)
    if os.environ.get("INDEXNOW_KEY"):  # verification file for IndexNow (see ping_indexing.py)
        (ROOT / "dist" / f"{os.environ['INDEXNOW_KEY']}.txt").write_text(os.environ["INDEXNOW_KEY"])

    # offline single file: logos embedded, jobs open inside the page
    logos = {f.stem: "data:image/png;base64," + base64.b64encode(f.read_bytes()).decode()
             for f in sorted((ROOT / "data" / "logos").glob("*.png"))}
    data["logos"] = logos
    # posts split from one notice share its job description: store each description once
    jd_table, jd_index = [], {}
    for j in data["jobs"]:
        jd = j.pop("jd", None)
        if not jd:
            continue
        shared = {k: v for k, v in jd.items() if k not in ("vacancy", "post_qualification")}
        key = json.dumps(shared, sort_keys=True, ensure_ascii=False)
        if key not in jd_index:
            jd_index[key] = len(jd_table)
            jd_table.append(shared)
        j["jd_ref"] = jd_index[key]
        j["jd_post"] = {k: jd[k] for k in ("vacancy", "post_qualification") if jd.get(k)}
        for k in ("alias_ids", "hosts", "also_urls", "first_seen", "notice_id"):
            j.pop(k, None)
    data["jds"] = jd_table
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    frag = (template.replace("/*__DATA__*/", blob).replace("<!--SEO_LIST-->", "").replace("<!--SEO_INTRO-->", "")
            .replace("<!--SEO_LINKS-->", "").replace("/*HOME*/", "#").replace("/*NAV_PSU*/", "#")
            .replace("/*NAV_CENTRAL*/", "#").replace("/*NAV_STATE*/", "#"))
    off = ROOT / "dist" / "offline"
    off.mkdir(parents=True, exist_ok=True)
    (off / "fragment.html").write_text(frag)
    head, _, body = frag.partition("</style>")
    (off / "sarkari-jobs-board.html").write_text(
        '<!doctype html>\n<html lang="en-IN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
        f"{head}</style></head>\n<body>{body}</body></html>\n")
    print(f"built site: {data['notices']} notices -> {stats['jobs']} job pages (one per post), {stats['landing']} landing pages, {stats['urls']} sitemap URLs; "
          f"{with_jd} jobs with descriptions; {data.get('deduped_by_link', 0)} merged by shared official link; "
          f"{len(logos)} logos; base {base}")


if __name__ == "__main__":
    main()
