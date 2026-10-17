# Figures for the plugins-end-to-end article

3 images, in reading order, for `docs/publications/pyvar-plugins-end-to-end-medium-article.md`. The HTML in `../../medium-ready/` already embeds them; use this list to drag each file to its position if Medium does not carry an image across on paste. Medium takes PNG/JPG only (no SVG).

Regenerate every image with `python scripts/generate_plugin_flow_figures.py` (needs `matplotlib`). Every number in them is read from the code when they are drawn: the function count from `portal/functions.json`, the example counts from `scripts/skill_specs/`, the key lifetime and cache TTLs from `config.py` and `api/middleware/api_keys.py`.

This list is derived from the article's image markers (file, alt text, caption, position).

## 1. `plugins-end-to-end-header.png`

- **Where:** under the title and subtitle
- **Caption:** What the plugins rest on, read from the code.
- **Alt text:** Four tiles: 385 functions in 8 domains; 16 worked examples in the skills, with 28 requests run against the real application on every test run; an API key lifetime of 365 days with up to 5 active keys per account; and a longest wait for a tier change of 60 seconds.

## 2. `plugins-end-to-end-setup-flow.png`

- **Where:** right after: “## Getting a key”
- **Caption:** Figure 1. The path a new user takes. The skill tells Claude each step.
- **Alt text:** Flow chart in six steps: install the plugin; ask a risk question and the skill tells Claude to look for PYVAR_API_KEY; with no key, go to pyvar.com and sign in with Google or an emailed link; create a key on the dashboard, shown once and valid 365 days; set PYVAR_API_KEY or paste it when the MCP plugin asks; Claude makes the call. A revoked or expired key returns 401 and sends you back to the sign-in step.

## 3. `plugins-end-to-end-key-check.png`

- **Where:** right after: “A session token is just decoded. A key needs the account's tier, so there is a lookup per call, and …”
- **Caption:** Figure 2. A cache hit costs one Redis read and no database connection. Only misses reach the database.
- **Alt text:** Flow chart: a Bearer pyvar_ key is hashed with SHA-256 and looked up in Redis. A hit returns the account and tier. A miss goes to the database by hash; found is cached for 60 seconds and returned; not found returns 401, cached for 30 seconds, and past 30 bad keys a minute from one address returns 429; a database error returns 503.
