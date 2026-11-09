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
(`pyvar-cdk/stacks/edge_stack.py`) has no bot or IP-reputation rules: the managed Common and
KnownBadInputs sets and two rate limits (100 requests per 5 minutes per IP, 6,000 shared) that a 19-page crawl would
not reach. The log check below confirmed it.

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

## Googlebot log check (result, 2026-11-09)

A read-only check by the AWS agent of the prod edge and origin for 2026-09-25 to 11-09 (46 days). Distribution
`E34RNOFIQN929N` (`pyvar.com`, `www.pyvar.com`), WebACL `pyvar-prod-waf`. Logs that exist: CloudFront standard logs
(complete for every day of the window, kept indefinitely, 16.4 MB since 2026-08-11). Logs that do not: WAF
logging, ALB access logs, CloudFront real-time logs. So the answer rests on the complete CloudFront logs plus the
WAF and ALB metrics.

**Googlebot was not blocked or throttled.**

- 540 requests carried a Google user agent (Googlebot, Google-InspectionTool, GoogleOther). **420 came from 25 IPs
  inside Google's published ranges**; 120 came from 29 IPs outside them (spoofed, probing `.env` paths, 30 of them
  answered 403 by the edge).
- The 420 genuine requests got 200, 301 (http to https), 304 or 404, **never 403, 429 or 5xx**. Response time
  p50 0.23 s, p95 0.49 s, max 0.98 s. One Google IP made at most 48 requests in 5 minutes (the WAF limit is 100).
  Every request used the host `www.pyvar.com`, none `pyvar.com`.
- The WAF's bot metrics count verified Googlebot 258 allowed, 0 blocked, 0 unverified.
- The only 404s to genuine Google were `/robots.txt` on 09-25, 09-27 and 09-29; it has returned 200 since.

**What Google actually did.**

- It read `sitemap.xml` 18 times on 18 days (09-30 to 11-08), always 200, and `robots.txt` on 28 days.
- Before 11-09 it fetched **one** of the 15 never-crawled pages: `domain-market-risk.html`, twice (200) on 10-17.
  That is Google-side scheduling, not blocking. This is an inference from the pattern; the logs do not state a
  reason.
- On **11-09 between 11:12 and 11:20 UTC it fetched 12 of the 15** (all except `plugins`, `privacy`, `terms`), all
  200, by Google-InspectionTool (2 each) and Googlebot (1 each). That matches the manual "Request indexing" clicks,
  and it fetched the versions served before this change was deployed. The three not yet fetched were never
  requested by genuine Google.
- It also fetched `pyvar.css`, `pyvar.js`, `functions.json` and `public/status.json`, so it does render the pages.
- Not explained: `domain-market-risk.html` was fetched on 10-17 although Search Console lists it as never crawled.

**The rest of the edge and origin, for the record** (none of it affects crawling):

- The WAF evaluated 64,503 requests and blocked 11,558 on 37 days: scanners (CommonRuleSet 4,357, KnownBadInputs
  3,346, RateLimit 3,855, AggregateRateLimit 0), with peaks on 10-12 and 10-24.
- CloudFront 5xx on 3 days, 1 or 2 requests each; ALB target 5xx 4 and ELB 5xx 5 in the whole window.
- The ALB listener answered 263,941 requests with 403, 3.9 times all CloudFront traffic: requests without the
  origin-verify header, i.e. direct hits on the ALB that bypass CloudFront, refused as designed.
- Target latency p95 at most 0.22 s on 45 days; 4.2 s on 10-05 (a burst of 3,305 requests in one hour); a daily
  maximum of 4 s or more on 10 days. Healthy hosts at least 2 every day; the ECS service 2/2, with four rolling
  deployments since 10-31 of about 4 minutes each and no failed tasks. CPU maximum reaches 99 to 100% on 21 days
  (average 1.2%); memory maximum 65 to 71%.
- Unexplained: WAF metrics labelled by bot name although the WebACL has no Bot Control rule.

**Not done:** per-rule attribution of the 403s (no WAF logs; enabling them would store client IPs and cost
storage, so it was not proposed), ECS history before 10-31 (stopped tasks are not kept), anything in AWS.

**Conclusion:** the edge and origin are not why 15 pages were never crawled. What is left is Google's own
crawl priority for the site, which is what the plain-HTML links in this change address.

## After merging

Merging starts a CodePipeline run (`portal/` is outside the excluded directories). In Search Console:

- Request indexing for `plugins.html`, `privacy.html` and `terms.html`, the three not yet fetched (the quota is
  about 10 a day per property), and, once this is deployed, again for `/`, `guides.html` and `plugins.html`, so
  Google sees the new links.
- Confirm the sitemap shows "Success" with 19 URLs.
- Re-inspect the pages in a week or two. A page that moves from "Discovered" to "Crawled - currently not
  indexed" has been judged on its content, not its crawl priority; the thin static text of the domain pages
  (about 300 words, the function lists being written by JavaScript) is then the lead.
- Re-export "Discovered - currently not indexed": a "last crawled" date appearing, and the count falling from 15,
  is the signal. New sites often take weeks.
