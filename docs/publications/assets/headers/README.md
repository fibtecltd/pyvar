# Header images

6 header images, one per article, each directly under the title and subtitle. The Medium-ready HTML in `../../medium-ready/` already embeds them; use this list to drag a file to its position if Medium does not carry an image across on paste. Medium takes PNG/JPG only (no SVG).

Regenerate every image with `python scripts/generate_article_headers.py` (needs `matplotlib`). Every number in them is read from the code when they are drawn: the plugin manifest, the function catalogue, the skill specs, `config.py`, the `pyvar-client` and `pyvar-jupyter` packages and `pyvar-full/docker-compose.yml`.

The other articles' headers, and ideas for the five that have none, are in `../../header-images.md`.

## 1. `header-pyvar-client-guide.png`

- **Article:** `pyvar-client-guide-medium-article.md`
- **Where:** under the title and subtitle
- **Caption:** pyvar-client at a glance, read from the code.
- **Alt text:** Four tiles: 385 functions, one method each, in 8 domain namespaces plus var for the async Monte Carlo job; 3 automatic retries with exponential backoff from 0.5 seconds, idempotent calls only; 1 runtime dependency, httpx at version 0.27 or later; and the current version, 0.2.0, which reads PYVAR_API_KEY from the environment.

## 2. `header-pyvar-domain-examples.png`

- **Article:** `pyvar-domain-examples-medium-article.md`
- **Where:** under the title and subtitle
- **Caption:** Nine notebooks at a glance, read from the code.
- **Alt text:** Four tiles: 9 worked example notebooks, 01 to 09 in pyvar-jupyter/examples; 8 risk domains in the catalogue; 385 functions available; and pyvar-jupyter version 0.1.0.

## 3. `header-pyvar-jupyter-guide.png`

- **Article:** `pyvar-jupyter-guide-medium-article.md`
- **Where:** under the title and subtitle
- **Caption:** pyvar-jupyter at a glance, read from the code.
- **Alt text:** Four tiles: 3 magics (%pyvar, %pyvar_base_url and %pyvar_key); 9 worked example notebooks in pyvar-jupyter/examples; 385 functions from one magic, any domain.function with parameters as key=value or JSON; and the current version, 0.1.0.

## 4. `header-pyvar-plugins-live-recent-updates.png`

- **Article:** `pyvar-plugins-live-recent-updates-medium-article.md`
- **Where:** under the title and subtitle
- **Caption:** pyvar today at a glance, read from the manifest, the config and the compose file.
- **Alt text:** Four tiles: 14 plugins (8 domain skills, 5 architecture skills, 1 MCP server); 900 seconds, the longest a result stream waits; 5 services in one docker compose up (migrate, pyvar-api, worker, redis, postgres); and a 365-day API key lifetime.

## 5. `header-pyvar-plugins.png`

- **Article:** `pyvar-plugins-medium-article.md`
- **Where:** under the title and subtitle
- **Caption:** The plugins at a glance, read from the manifest and the code.
- **Alt text:** Four tiles: 14 plugins in one marketplace (8 domain skills, 5 architecture skills, 1 MCP server); 385 functions behind them in 8 domains; 16 worked examples in the domain skills, with 28 requests run against the real application on every test run; and uvx, which starts the MCP server from PyPI.

## 6. `header-pyvar-rest-api-guide.png`

- **Article:** `pyvar-rest-api-guide-medium-article.md`
- **Where:** under the title and subtitle
- **Caption:** The REST API at a glance, read from the code.
- **Alt text:** Four tiles: 385 POST endpoints under /api/v1/<domain>/<function>; 8 domain prefixes; 10 free-tier calls a day, 500 on Pro in one shared bucket across every endpoint; and 10,000 simulations per Monte Carlo call on the free tier, 100,000 on Pro and 500,000 on Enterprise.
