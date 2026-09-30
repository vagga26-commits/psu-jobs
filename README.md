# Sarkari Jobs Board

A crawler plus a static website that lists open Indian government job notices:
central government, state governments and UTs, PSUs and PSU banks, railways,
defence and police, UPSC/SSC/state PSCs, teaching and research, health, courts
and local bodies. The site follows the naukri.com job-search layout.

```
crawler/
  sources.yaml     which pages to crawl (aggregators + 24 official PSU career pages)
  crawl.py         fetch → parse → normalise → dedupe → data/jobs.json
  parsers/table.py     header-driven parser for aggregator tables
  parsers/official.py  keyword heuristic for PSU career pages (no per-site selectors)
  orgs.py          PSU registry: aliases → short name, full name, sector
  normalize.py     dates, vacancies, apply mode, stable ids, merge
  build_site.py    inlines jobs.json into web/template.html → dist/
web/template.html  the site (search, sector chips, qualification level, apply mode, sort)
tests/             fixtures + pytest
.github/workflows/crawl.yml   crawl 3×/day and deploy to GitHub Pages
```

## Run locally

```bash
pip install -r requirements.txt
python -m pytest -q tests
python crawler/crawl.py          # writes data/jobs.json
# offline rebuild from saved snapshots (no network):
python crawler/crawl.py --only snapshot --snapshot data/snapshot.tsv --snapshot data/snapshot_govt.tsv
python crawler/fetch_details.py  # job descriptions + original Apply links
python crawler/fetch_logos.py    # downloads employer logos (optional)
SITE_URL=https://jobs.example.in python crawler/build_site.py   # dist/ (site) + dist/offline/
python -m http.server -d dist 8000   # preview at http://localhost:8000
```

Options: `--only aggregators|official`, `--snapshot file.tsv` (merge rows you
collected by hand; columns `post_date org title qualification last_date url source only_known`).

## Deploy (free)

1. Push this folder to a GitHub repo.
2. Settings → Pages → Source: **GitHub Actions**.
3. Actions → *Crawl PSU jobs* → Run workflow. It then runs at 05:47, 11:47 and 17:47 IST.

Any static host works too: run the two scripts on a cron and upload `dist/`.

## How it works

- **Dedup**: each job gets an id from `org + normalised title + last date`, so
  the same notice from an aggregator and an official page merges into one row
  with both sources.
- **Carry-forward**: each run merges with the previous `jobs.json`, so a source
  that is down for a run doesn't make listings disappear. Jobs drop off once
  their last date passes.
- **Politeness**: honours robots.txt, identifies itself with a User-Agent,
  1.5 s delay between requests, 3 retries with backoff.
- **Filtering**: known non-PSU bodies (CSIR labs, IITs, private/co-op banks)
  are excluded; the bank aggregator only keeps organisations in `orgs.py`.

## Sources

`crawler/sources.yaml` lists every source; set `enabled: false` to skip one.

- **Table aggregators** (`parser: table`): FreeJobAlert PSU, bank, government, latest, railway,
  defence, teaching and 23 state pages.
- **Link-list aggregators** (`parser: links`): SarkariResult, SarkariExam, Sarkari Naukri Blog,
  FreshersNow, Adda247, Testbook, Jagran Josh, Freshersworld. Titles are split into organisation,
  post and vacancies (`parsers/links.py`); last dates come from each notice's detail page
  (fetched once, cached in `data/jd.json`, at most `detail_limit` new pages per source per run).
- **Official sites** (`official`): 24 PSU career pages, UPSC, RRB, IBPS, DSSSB and 25 state PSCs /
  subordinate service boards.
- Switched off until a JavaScript-capable fetch is added: Naukri govt jobs, Employment News,
  National Career Service, SSC.

The first live run will show which URLs return rows (see the Actions log); adjust `include`,
`exclude` or the URL for any source that returns 0.

## Removing duplicates

The same notice appears on many sites under different titles ("SSC CHSL 10+2 Online Form 2026
(2536 Posts)" vs "CHSL – 2536 Posts"), often with a deadline extended on one of them. `normalize.merge`
removes duplicates in four passes:

1. **Exact:** same article URL, or same organisation + title + last date.
2. **Cross-site fuzzy** (only between different sites – two notices on one site are never merged):
   same organisation and same vacancy count within 21 days; same organisation and same last date
   with overlapping (or generic) titles; strongly overlapping titles; or an identical, large
   vacancy count. Known organisations must match by name (SBI ≠ Bank of India).
3. **Unique same-day match:** a notice seen on one site whose organisation has exactly one notice
   with that last date on another site.
4. **Shared advertisement PDF** (`merge_by_links`, after job descriptions are attached): two sites
   linking to the same official notification document. Shared application portals and login pages
   are ignored.

Merged jobs keep every source, the later deadline, the more specific title and the richer job
description. Closed notices are dropped before merging.

## One job per designation

Many notices recruit for several posts ("Management Trainee & Assistant Officer – 77 Posts").
`normalize.split_by_post` (run in `build_site.py`, after duplicates are removed) turns every row
of the notice's vacancy table into its own job: its own page, title, number of posts and
qualification, sharing the notice's dates, fee, age limit and Apply link. Each post page lists the
other posts in the same notice. Category rows (UR/OBC/SC/ST/EWS/Total…) are ignored, identical post
names are added together, and at most 40 posts are split per notice (the rest are mentioned).
Notices without a vacancy table stay as one job.

## Classification

`crawler/classify.py` gives every notice:

- **Job type** (`level`): Central Govt, State Govt or PSU. PSUs come from the
  registry in `orgs.py`; state bodies are matched by name (state PSCs, boards,
  districts, high courts, state universities, Anganwadi, municipal bodies).
- **Department**: Public Sector Undertakings, Banking & Finance, UPSC/SSC/PSC,
  Judiciary & Legal, Railway, Defence & Police, Medical & Health, Anganwadi &
  Social Welfare, Municipal & Local Bodies, Teaching & Research, or
  Administration & Others. A source's `category` in `sources.yaml` is the
  fallback.
- **Location**: the state from state pages; a central notice listed under
  three or more states becomes "All India".

## SEO

`crawler/sitegen.py` (called by `build_site.py`) turns the data into a static,
crawlable site in `dist/`:

| Pages | Example URL | Targets |
|---|---|---|
| One page per job | `/job/canara-bank-apprentice-recruitment-2026-3-500-posts-1198be/` | "<org> <post> recruitment 2026"; **JobPosting** data for Google for Jobs |
| Job type | `/psu-jobs/`, `/central-govt-jobs/`, `/state-govt-jobs/` | head terms |
| Departments | `/railway-jobs/`, `/banking-and-finance-jobs/`, `/defence-and-police-jobs/` | category searches |
| States | `/uttar-pradesh-govt-jobs/` (state posts + all-India notices) | "<state> govt jobs" |
| Qualification | `/10th-12th-pass-govt-jobs/`, `/graduate-govt-jobs/`, `/btech-be-govt-jobs/` | "10th pass govt jobs" |
| Organisations (2+ notices) | `/ntpc-recruitment/`, `/sbi-recruitment/`, `/upsc-recruitment/` | "<org> recruitment" |
| Time-based | `/closing-soon/`, `/latest-govt-jobs/`, `/walk-in-interview-govt-jobs/` | freshness queries |

Every page has a unique `<title>` (~60 chars) and meta description, canonical
URL, Open Graph/Twitter tags, breadcrumbs and JSON-LD (JobPosting with
`validThrough`, `totalJobOpenings`, `employmentType` where clear; BreadcrumbList;
ItemList; FAQPage; WebSite). Job pages get an original fact-based intro plus an
FAQ block. The home page ships the first 20 jobs as plain HTML (works without
JS) and a footer link hub that reaches every landing page. Also generated:
`sitemap.xml`, `robots.txt`, `feed.xml` (RSS), `404.html`, `assets/og.png`.
Expired notices are dropped on the next build, so their pages return 404.

**Setup after the first deploy**

1. Use a custom domain (Settings → Pages): a `github.io/<repo>` project site
   can't serve `robots.txt` at the domain root. Put the domain in a repository
   variable `SITE_URL` (Settings → Secrets and variables → Actions → Variables),
   e.g. `https://jobs.example.in`.
2. Add the site to **Google Search Console** and **Bing Webmaster Tools** and
   submit `https://<domain>/sitemap.xml`.
3. Fast indexing (optional, recommended for jobs):
   - `INDEXNOW_KEY` secret: any random 32-character string. Bing and Yandex are pinged every run.
   - `GOOGLE_INDEXING_SA` secret: a service-account JSON added as an Owner in
     Search Console. New job pages are pushed to Google's Indexing API
     (200 per day by default).
4. Test a job page with Google's Rich Results Test.

## Job description pages and Apply Now

Clicking a job opens its description page (`#job-<id>`): summary, key details,
important dates, vacancy table, eligibility, age limit, fee, selection
process, how to apply, official links and similar jobs.

`crawler/fetch_details.py` fetches each new aggregator article and parses it
with `parsers/article.py`; `crawler/jd.py` cleans the result into
`data/jd.json`. **Apply Now always points at the employer's own site**, never
the aggregator: application portal → official notification → application form
→ official website (company-site notices use the notice's own page). Email-only
applications are listed under Contact.

## Logos

`crawler/logos.py` maps ~130 employers (and families such as AIIMS, DRDO,
CSIR, railway zones) to their website domain. `crawler/fetch_logos.py`
downloads each site icon into `data/logos/`, and `build_site.py` embeds them
in the page. Without embedded files the page loads icons from Google's favicon
service at view time. Unknown employers (mostly district and local bodies) show
an initials tile. Add a domain to `DOMAINS` to give an employer a logo.

## Company sites vs aggregators

Every job carries `source_types`: `official` (the PSU's own careers page),
`aggregator` (a job portal), or both. The site's **Found on** filter uses it:
All · Company sites · Aggregators · On both.

- The same notice on both kinds is merged with a fuzzy title match (same org,
  shared title words, same last date or same posting date). Its button links
  to the official notice, with the aggregator summary as a second link.
- Company pages often omit last dates. Those notices stay listed 45 days after
  posting (60 if marked Ongoing/Active); rows marked Closed are skipped; rows
  with no date at all are dropped.

## Adding a source

Append to `sources.yaml`. A new aggregator with a table that has "Post" and
"Last Date" headers works with `parser: table`. A new PSU careers page works
with the `official` list. Add new organisations to `orgs.py` so they get the
right sector and full name.

## Known limits

- Official PSU sites often block data-centre IPs or render lists with
  JavaScript. The official parser is a heuristic; the aggregator feed carries
  most of the structured data (qualification, vacancies).
- Vacancy counts come from titles and URL slugs, so some notices show none.
- Always link users to the official advertisement before they apply.
