# Smithery (smithery.ai) — pyvar-mcp submission content

**Draft, not submitted.** Prepared at Filippo's request for a single,
most-relevant alternative MCP directory — not a Claude-specific channel,
so it doesn't compete with or duplicate the still-pending
`claude-plugins-community` submission (see
`docs/plan-plugin-marketplace-status-and-submission.md`). Smithery was
picked over mcp.so / PulseMCP / Glama / `punkpeye/awesome-mcp-servers`
because it's the one with real structured submission content worth
drafting — the others either auto-index from GitHub with no form to fill
in, or want a one-line list entry, not a manifest. It's also one of the
most-used general MCP registries (not Claude-specific — reachable from
Cursor and any other MCP client too), verified live via web search this
session, not from training-data memory.

## What's now in the repo, ready to review

- **`plugins/mcp/Dockerfile`** — containerises `pyvar-mcp` for Smithery's
  `container` runtime. Verified this session (not just written and hoped):
  `pip install .` against the exact same `pyproject.toml`/`pyvar_mcp/`
  tree the Dockerfile copies succeeds in a clean virtualenv, and the
  installed `pyvar-mcp` console script resolves and fails *only* on the
  expected, documented thing — a missing `PYVAR_API_KEY` — confirming the
  packaging and entrypoint are correct. (The actual `docker build` itself
  could not be run — no Docker daemon in this session's sandbox — but the
  identical `pip install .` step it performs was verified directly.)
- **`plugins/mcp/smithery.yaml`** — the manifest Smithery's deploy flow
  reads: `container` runtime pointing at that Dockerfile, `stdio` transport
  (matching how `.claude-plugin/plugin.json`'s `mcpServers` config already
  talks to it locally), and a `pyvarApiKey` config field mapped straight
  onto the same free-tier key source the Claude plugin already documents
  (`https://www.pyvar.com#get-api-key`) — no new auth mechanism invented.

## Submission form content (for `smithery.ai/new`, once connected to GitHub)

- **Name:** pyvar-mcp
- **Description:** MCP server exposing 385 regulatory-grade financial risk
  functions (VaR, credit risk, derivatives pricing, liquidity, operational
  risk, portfolio analytics, ALM, regulatory capital) from the open-source
  pyvar.com platform, as MCP tools — via the live pyvar REST API, not a
  bundled copy of the compute engine.
- **Category:** Finance / Data & APIs (Smithery's own taxonomy — confirm
  exact category names when actually on the submission page; not
  independently verified this session).
- **Repository:** https://github.com/fibtecltd/pyvar (path: `plugins/mcp`)
- **Auth method:** API key (`pyvarApiKey`, free tier, no card required —
  see `smithery.yaml`'s `configSchema`)
- **License:** Apache-2.0

## Security / trust disclosure (same facts as the Claude marketplace submission — not re-derived)

- Only external dependency is the pyvar REST API itself
  (`https://www.pyvar.com`) — no third-party services, no telemetry.
- **Data sent:** whatever parameters the caller provides to a function
  call, over HTTPS with the user's own API key — exactly as calling the
  REST API directly. No portfolio or position data retained beyond pyvar's
  documented job-result TTL.
- Open source, Apache-2.0-licensed, publicly auditable — every tool's
  behaviour traces to the actual REST API route it calls.

## What this session could not verify — check before submitting

1. **Smithery's exact category taxonomy and any other required form
   fields** — not independently confirmed against the live `smithery.ai/new`
   page (not fetchable from this session's sandbox — `claude.com` and
   `clau.de` were reachable-blocked domains this session, and
   `smithery.ai/new` itself requires a connected GitHub session to render
   meaningfully anyway).
2. **Whether Smithery's automated build actually succeeds** — the
   `Dockerfile`/`smithery.yaml` pairing is standard and the underlying
   `pip install .` step is verified, but Smithery's own build pipeline
   (clone → detect `container` runtime → build → deploy) has not been run
   end-to-end. Worth watching the first deploy attempt rather than assuming
   success from this doc alone.
3. **Whether a publisher account / GitHub connection introduces terms you
   want to review first** (Smithery's own ToS, data-handling terms for
   hosted execution of your Dockerfile) — not reviewed this session; skims
   of Smithery's public docs found no red flags, but "no red flags found in
   a skim" isn't the same as "reviewed and accepted."

## Definition of done

- Filippo has reviewed `plugins/mcp/Dockerfile` and `plugins/mcp/smithery.yaml`
  and is comfortable with what gets built and hosted.
- Connected GitHub at `smithery.ai/new`, selected `fibtecltd/pyvar`, pointed
  the deploy at `plugins/mcp/`, and confirmed the automated build succeeds.
- Filled in the submission form content above (adjusted for whatever the
  live form's actual field names/categories turn out to be).
- `docs/plan-plugin-marketplace-status-and-submission.md` updated with the
  outcome, same as every other verified-fact update this session made.
