# Search Console: why 15 pages were never crawled (2026-11-09)

A Search Console email reported a new reason, "Alternate page with proper canonical tag". Four "Coverage
Drilldown" exports for `pyvar.com` (all known pages) were attached; they changed the picture. The email's reason
is harmless. A different one is not: Google has never crawled 15 of the 19 sitemap pages.

## What the exports say

| Export | URLs | Meaning |
|---|---|---|
| Discovered - currently not indexed | 15, last crawled empty | Google found them (the sitemap) and has not fetched them. 16 on 10-04, 18 on 10-05 (privacy and terms added), 15 from 10-10, unchanged to 11-06 |
| Alternate page with proper canonical tag | `https://www.pyvar.com/index.html` | First counted 10-24, last crawled 11-07. A duplicate of `/` whose canonical is `/`; accepted, nothing to fix |
| Page with redirect | `http://pyvar.com/`, `https://pyvar.com/` | The apex redirects (301, by the registrar's forwarding proxy) to `https://www.pyvar.com/`. Expected |
| Crawled - currently not indexed | `http://www.pyvar.com/`, crawled 2026-06-13 | A stale http URL that now redirects. Ignore |

The 15 are the five guides, `guides.html`, `plugins.html`, `local.html`, `privacy.html`, `terms.html` and five of
the eight domain pages (`domain-alm`, `credit-risk`, `derivatives`, `market-risk`, `portfolio-analytics`). The four
sitemap pages in none of the exports (the homepage, `domain-liquidity-risk`, `domain-operational-risk`,
`domain-regulatory`) are presumably indexed; no "Indexed" export was supplied. Three pages left "discovered"
between 10-09 and 10-10 and nothing has since: in a month Google crawled almost nothing, although it did fetch
`/index.html` and the apex URLs on 11-06 and 11-07.

"Discovered" means the page itself has not been evaluated, so on-page content is not the cause. For a small,
low-authority site the usual cause is crawl priority.

## What was checked and found sound

From outside, 2026-11-09: all 19 sitemap URLs return 200 in 0.2 to 0.6 s for a normal and a Googlebot user agent;
each names itself as canonical; none is noindex; titles are unique, descriptions present, one `h1` each; the
guides carry 1,000 to 1,800 words; `robots.txt` allows everything except `/dashboard.html`; http and the apex
redirect to `https://www.pyvar.com` (the deliberate canonical host). The CloudFront WAF
(`pyvar-cdk/stacks/edge_stack.py`) has no bot or IP-reputation rules, only two rate limits (100 requests per
5 minutes per IP, 6,000 shared) that a 19-page crawl would not reach.

## What was weak

- **Almost no plain-HTML links between pages.** The nav and footer are written by `document.write` scripts
  (`portal/pyvar.js`), so a crawler that does not run scripts saw none of them. Each domain page had one inbound
  link, from the homepage; `local.html` had none; the guides five.
- **Every page linked home as `index.html`** (57 links on 18 pages), a duplicate of `/`. That is the one
  "alternate page" in the report, and it spent link weight on a URL that is not canonical.
- **Thin static text on the domain pages**, about 300 words each, because the function lists are filled in by
  JavaScript. Not changed here.
- **No `<lastmod>` in the sitemap.** Google ignores `changefreq` and `priority`.

These can lower crawl priority; they were not proved to be the cause.

## What this change does

- Every home link is now `/` (nav, logo, "Get API key", footer, in-page buttons, `pyvar.js`).
- `scripts/sync_portal_seo.py` generates a plain-HTML "all pages" strip (`<nav class="site-links">`) above the
  footer of every page except the dashboard: every page now links to every page without JavaScript. Checked in a
  browser with scripts off: 19 links on each page, `local.html` and each domain page linked from every page,
  none to `index.html`; with scripts on there is still one footer, and Home goes to `/`.
- `portal/sitemap.xml` gains `<lastmod>` per page, taken from git (today for a page with uncommitted changes).
  All pages show 2026-11-09 because all were changed here.
- `tests/test_portal_links.py` runs the script's checker (it needs no git, so it runs in CodeBuild): canonical per
  page, block present and current, no `index.html` links, sitemap equal to the pages with valid dates; and it
  breaks a copy of the portal on purpose to show each check can fail.
- After a page changes, run `python scripts/sync_portal_seo.py` and commit; `--check` only reports.

## Not done

- A 301 from `/index.html` to `/` (possible only on pyvar.com, in `main.py`). With the links gone the duplicate is
  no longer linked; the "alternate page" status will stay until Google recrawls it, and is harmless.
- Rendering the function lists into the domain pages' static HTML.
- `fibtec.co.uk` (the `fibtec-site` repo) has the same `index.html` link pattern. Its `archive/` copies are
  blocked by `robots.txt` and are not a cause. Not touched here.
- Noticed, unrelated and unchanged: on a 390 px phone the homepage scrolls sideways by 209 px and the domain pages
  by 67 px (identical on unchanged master).

## Googlebot log check (pending)

Whether Googlebot was blocked, throttled or given errors by the edge or origin from 2026-09-25 on is not visible
from outside. A read-only check of the WAF, CloudFront, ALB and ECS metrics and any request logs was handed to
the AWS agent; its result goes here when it reports.

## After merging

Merging starts a CodePipeline run (`portal/` is outside the excluded directories). In Search Console, request
indexing for the 15 pages (the quota is about 10 a day per property, so the rest go in over a second day),
confirm the sitemap shows "Success" with 19 URLs, and re-export "Discovered - currently not indexed" in a week or
two: a "last crawled" date appearing, and the count falling from 15, is the signal. New sites often take weeks.
