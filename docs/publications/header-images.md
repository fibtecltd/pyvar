# Header images for the Medium articles

Every article should open with a header image directly under its title and subtitle. Eleven have one (an image file in the repository); the other six have an idea below, written so a designer, or `scripts/generate_article_headers.py`, can build it. Every number in an idea comes from the article it is for.

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
| `pyvar-streaming-results-medium-article.md` | Included: `assets/headers/header-pyvar-streaming-results.png` |
| `pyvar-overview-medium-article.md` | Included: `assets/headers/header-pyvar-overview.png` |
| `pyvar-technical-deepdive-medium-article.md` | Idea 1 |
| `pyvar-iron-triangle-medium-article.md` | Idea 2 |
| `pyvar-local-release-medium-article.md` | Idea 3 |
| `pyvar-full-docker-medium-article.md` | Idea 4 |
| `pyvar-post-launch-lessons-medium-article.md` | Idea 5 |
| `pyvar-assistant-medium-article.md` | Idea 6 |

The eight images in `assets/headers/` come from `python scripts/generate_article_headers.py`. Seven are fact tiles in the house style (slate and clay on white, the same grid as the plugins-end-to-end header), and each number is read from the code when the image is drawn. The eighth, the overview article's, is a picture (a dot-matrix bell curve, source in `assets/headers/source/`); the overview's fact tiles are its second image, `assets/overview/at-a-glance.png`. Medium takes PNG or JPG, not SVG.

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

### 6. The assistant that never answers live

**Concept:** three outlined buttons ("What it does", "When to use it", "Compare with") on the left, an arrow to one small slate file tile labelled "one 3 KB file", and a clay-outlined box crossed out on the right labelled "model call". A thin strip under the arrow shows the 1,154 answers as a row of small squares, two of them in clay for the two static answers.
**Text on the image:** "1,154 answers, written before you clicked." and, small, "0 model calls when you do."
**Why it fits:** the article is about an assistant whose answers are static files read on a click, with no model in the request path; the counts (1,154 answers, 2 static) come from the bank's manifest.
**Alt text:** Three buttons leading to a single small file, with a crossed-out box marked model call, above a row of 1,154 squares of which two are highlighted as static answers.
**Candidate received 2026-11-13, not used as it stands:** a 3D illustration of an assistant character beside a capability grid and a chat in which a typed request ("Show me a risk analysis for my portfolio") gets generated code, a chart and a table of figures (VaR 12.5%, ES 16.8%, Sharpe 1.32). It shows what the article says the assistant does not do: take typed requests (the typed box is off everywhere), run analyses, write code or return figures, and the figures and the code (`px` and `pv` aliases, a `pv.risk.analyze` call) are invented, not from pyvar. The tiles "Stay Compliant", "Deploy Anywhere" and "Instantly" claim more than the article does. Its style (blue and orange 3D) also differs from the house style above. The regeneration brief below keeps what is good about it.

#### Regeneration brief for idea 6 (2026-11-13)

**Goal.** One image that tells a reader of the article what the assistant is: three fixed questions on a function's page, answered from a file written in advance. It must not suggest typing, live analysis, code, results, compliance or speed claims.

**Keep from the candidate.** The assistant character (brown wavy hair, round glasses, navy blazer, friendly open-hand gesture), the pyvar logo top left, the light background with soft blue glow, the palette (navy, mid blue, one orange accent) and the bell curve with the orange tail along the bottom.

**Remove.** The chat panel (typed requests, "Sure! I'll run the analysis"), the code block, the line chart, the results table and every number in them, the eight capability tiles, the tagline "MATHEMATICS / STATISTICS / INSTANTLY", "Ask. Analyze. Achieve." and the speech bubble "unlock the power of Pyvar".

**Layout (16:9, 1600 x 900 px, at least 1400 px wide for Medium; keep 80 px clear on every side).**
1. Left third: the character, standing, gesturing toward the centre. Small speech bubble: "Pick a function, then one of three questions."
2. Centre: a clean interface card, the widget as it is on the site: a function name (`kupiec_pof_test`), then **three controls**, two buttons labelled "What it does" and "When to use it" and one dropdown labelled "Compare with…"; the first is selected, and under it an answer panel with two or three lines of text (below).
3. Right third: a thin arrow from the card to one small file tile labelled "one 3 KB file", and beside it a box with a model or spark icon crossed out, labelled "model call".
4. Bottom: a thin band of **exactly 1,154** tiny squares (for example two rows of 577), two of them in the orange accent for the two static answers. Draw it with a script or in the design tool, not with the generator: a generator cannot count, and a band of 60 squares with two orange would show static answers as 3% of the bank when they are 0.17%. Headline under the band: "1,154 answers, written before you clicked." and under it, smaller, "0 model calls when you do."

**Text that goes on the image (exact; every number is in the article).** "What it does", "When to use it", "Compare with…", "one 3 KB file", "model call", "1,154 answers, written before you clicked.", "0 model calls when you do.", "2 static" (small, beside the orange squares). Answer panel, verbatim from the bank (`kupiec_pof_test`, explain): "...checks whether the number of VaR breaches in a backtest is consistent with what your VaR confidence level implies." No other numbers, formulas, percentages or code.

**Practical advice.** Image generators garble small text. Generate the picture without any text (ask for blank panels and empty labels), then add every string above in a design tool in one clean font, and place the logo from the repository. This also keeps the on-image text identical to the article.

**Prompt to paste into the image generator (picture only, no text).**

> A clean, friendly 16:9 illustration for a technical article. On the left, a smiling woman in a navy blazer, with brown wavy hair and round glasses, gestures with an open hand toward the centre; a small empty speech bubble beside her. In the centre, a modern software interface card with a blank title bar, two empty rounded buttons and one empty dropdown, the first button highlighted, and a white answer panel with three blank grey lines of placeholder text. To its right, a thin arrow leading to one small, simple file icon, and next to it a small box with a sparkle or chip icon crossed out by a diagonal line. A soft bell-curve line with an orange tail runs along the bottom. Light white and pale blue background with a soft glow; palette navy, mid blue and one orange accent; soft studio lighting, subtle shadows, a polished 3D-illustration look. No text, no letters, no numbers, no charts, no code, no chat messages anywhere.

**Check the result before using it.** (1) No invented figures, charts, code or chat anywhere. (2) Every word on it is one of the strings above, spelled exactly, after you have added them. (3) The third control is a dropdown, not a button, as on the site. (4) The band has exactly 1,154 squares and exactly two orange ones, drawn by you and not by the generator. (5) 1,154, 3 KB and "0 model calls" match the article's counts on the day of publishing (`/public/config` and the bank manifest). (6) The file is under about 1 MB. (7) If Medium's or the generator's terms ask for a note that the image was made with AI, add it to the caption.

**File, caption and alt text.** Save as `assets/headers/header-pyvar-assistant.png`, then uncomment the image line in the article. Caption: "Three questions, answered from files written before you clicked." Alt text: "A friendly assistant character beside a function page with three controls (What it does, When to use it, Compare with) that lead to a single small file, with a crossed-out box marked model call, above a row of squares for the 1,154 pre-written answers, two of them highlighted as static answers."

## Placement

Under the title and subtitle, before the update note. In the Markdown, `![alt](./assets/headers/<file>.png)` followed by an italic caption line; in the Medium-ready HTML, the same, with the image embedded. `assets/headers/README.md` lists each image with its caption and alt text.
