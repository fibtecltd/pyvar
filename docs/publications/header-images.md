# Header images for the Medium articles

Every article should open with a header image directly under its title and subtitle. Nine have one (an image file in the repository); the other five have an idea below, written so a designer, or `scripts/generate_article_headers.py`, can build it. Every number in an idea comes from the article it is for.

## Status

| Article | Header |
|---|---|
| `pyvar-buildstory-medium-article.md` | Included: `pyvar-buildstory-header.jpg` |
| `pyvar-plugin-examples-medium-article.md` | Included: `assets/plugin-examples/plugin-examples-header.png` |
| `pyvar-plugins-end-to-end-medium-article.md` | Included: `assets/plugins-end-to-end/plugins-end-to-end-header.png` |
| `pyvar-plugins-medium-article.md` | Included: `assets/headers/header-pyvar-plugins.png` |
| `pyvar-plugins-live-recent-updates-medium-article.md` | Included: `assets/headers/header-pyvar-plugins-live-recent-updates.png` |
| `pyvar-client-guide-medium-article.md` | Included: `assets/headers/header-pyvar-client-guide.png` |
| `pyvar-jupyter-guide-medium-article.md` | Included: `assets/headers/header-pyvar-jupyter-guide.png` |
| `pyvar-domain-examples-medium-article.md` | Included: `assets/headers/header-pyvar-domain-examples.png` |
| `pyvar-rest-api-guide-medium-article.md` | Included: `assets/headers/header-pyvar-rest-api-guide.png` |
| `pyvar-technical-deepdive-medium-article.md` | Idea 1 |
| `pyvar-iron-triangle-medium-article.md` | Idea 2 |
| `pyvar-local-release-medium-article.md` | Idea 3 |
| `pyvar-full-docker-medium-article.md` | Idea 4 |
| `pyvar-post-launch-lessons-medium-article.md` | Idea 5 |

The six images in `assets/headers/` come from `python scripts/generate_article_headers.py`. They are fact tiles in the house style (slate and clay on white, the same grid as the plugins-end-to-end header), and each number is read from the code when the image is drawn. Medium takes PNG or JPG, not SVG.

## Ideas

### 1. Inside pyvar's Compute Engine (technical deep dive)

**Concept:** one cold start against one warm call. A wide bar chart with two bars for `run_monte_carlo_var`: the first-ever call, 1.083 s, which includes compiling the kernel, and the warm call, 0.007 s. Under it, a thin strip of a worker count going from 0 up and back to 0 as the queue fills and drains.
**Text on the image:** "1.083 s the first time. 0.007 s every time after." and, small, "Workers scale to zero when the queue is empty."
**Why it fits:** the article is about the Numba kernel and a cluster that scales to zero; the benchmark table in the article gives both timings.
**Alt text:** Two bars for the Monte Carlo VaR kernel: 1.083 seconds for the first call, which compiles it, and 0.007 seconds for every call after; below them a line showing the worker count rising from zero and returning to zero.

### 2. Bending the Iron Triangle

**Concept:** a triangle with cost, speed and accuracy at its corners and one real number at each corner, drawn as an outlined slate triangle with a smaller clay triangle inside it.
**Text on the image:** "$900-1,000 a month" at cost, "100,000 paths in 2-10 s" at speed, "627 test assertions" at accuracy; title line "Pick two? Here are three numbers."
**Why it fits:** these are the three figures under the article's chart, each with its own date or source in the text.
**Alt text:** A triangle with cost, speed and accuracy at the corners: a production invoice of 900 to 1,000 dollars a month, a 100,000-path Monte Carlo VaR in 2 to 10 seconds, and 627 test assertions across 8 validation suites.

### 3. pyvar Local

**Concept:** a closed box (the Docker image) inside a plain building outline, with a dashed line leading out of the building to a cloud icon that is crossed out. No logos.
**Text on the image:** "No API key. No network call. No account."
**Why it fits:** the article is the offline package for institutions whose data-governance policy keeps position data inside the building; the line is the article's own summary.
**Alt text:** A container inside an office building outline, with a dashed line to a crossed-out cloud, and the words: no API key, no network call, no account.

### 4. pyvar Full

**Concept:** a terminal prompt line `docker compose up` above five stacked service tiles, one per service in the compose file: migrate, pyvar-api, worker, redis, postgres, with migrate drawn first and slightly offset because it runs once and exits.
**Text on the image:** "One command. The whole platform."
**Why it fits:** the article's point is that one `docker compose up` brings up the real API, worker, broker and database; the tile names come from `pyvar-full/docker-compose.yml`.
**Alt text:** A terminal line reading docker compose up above five service tiles: migrate, pyvar-api, worker, redis and postgres.

### 5. What Broke in the Two Weeks After Launch

**Concept:** a horizontal timeline of seven small tiles numbered #326 to #332, one per merged pull request, ending in a flag labelled v0.2.0; the tile for the feature that never deployed is outlined in clay with a thin cross-hatch.
**Text on the image:** "Seven pull requests. One feature that never ran." with "v0.2.0" on the flag.
**Why it fits:** the article is a checkable account of the seven pull requests after launch and what one of them taught the team about deployment.
**Alt text:** A timeline of seven pull requests, numbers 326 to 332, ending at a flag for version 0.2.0, with one tile marked as the feature that never deployed.

## Placement

Under the title and subtitle, before the update note and the draft-status block. In the Markdown, `![alt](./assets/headers/<file>.png)` followed by an italic caption line; in the Medium-ready HTML, the same, with the image embedded. `assets/headers/README.md` lists each image with its caption and alt text.
