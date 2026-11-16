# Plan: keyless access for the plugins, alternatives (proposal)

**Status: proposal, 2026-11-16. Nothing is built.** The owner rejected the first design (anonymous per-install keys, `docs/plan-anonymous-plugin-keys.md`) as not a clear win and asked for other options. This is a delegated review (Fable) of master `7e35bbc` and the public Claude Code, MCP and plugin-directory documentation; **[V]** marks what was checked and **[A]** what was assumed. The author spot-checked the unauthenticated rate limits (`api/middleware/rate_limit.py:236`, `:262`, `:295`), the WAF's per-IP and aggregate rules (`pyvar-cdk/stacks/edge_stack.py:105`, `:214`) and the `mcp` SDK dependency (`plugins/mcp/pyproject.toml`); they match.

**The one thing to take from it.** A stdio server (`uvx pyvar-mcp`) cannot use MCP sign-in, so as long as `pyvar-mcp` is a local launcher a key must be supplied some other way. Only a remote MCP server lets Claude Code itself run the sign-in and hold the token. That is the recommended option, and also the largest (an OAuth authorization server, three pipeline runs); a cheap local spike should settle the unverified client behaviour before anything is committed. No option clears the nine held skills, which are held at plugin level.

## 0. Findings that change the picture

1. **[V]** The stdio transport cannot use MCP sign-in. Spec: "Implementations using an STDIO transport SHOULD NOT follow this specification, and instead retrieve credentials from the environment." Claude Code: the OAuth flags "have no effect on stdio servers". While `pyvar-mcp` is `uvx pyvar-mcp==X` (`plugins/mcp/.claude-plugin/plugin.json:26-35`), a key in `userConfig` or a file is the only route.
2. **[V]** A plugin may declare a remote server: `type` `http` with an absolute `https://` `url` (pre-submission checklist; manifest reference lists `url`, `headers`, `headersHelper` for plugin `http` servers). Plugin servers appear in `/mcp`. **[A]** OAuth for a plugin-declared server is implied (the gateway sign-in section names "a server that … a plugin supplies"), never stated outright.
3. **[V]** Any `uvx`/`npx` launcher is "held for a reviewer" for ever ("Runs a pinned npx or uvx package"), independent of credentials. A `url` server has no launcher.
4. **[V]** A remote server can also be submitted as an **MCP connector**: "scanned automatically … and, by default, listed … as a Community connector". This path is separate from the plugin holds and reaches claude.ai, desktop and mobile.
5. **[V]** Unauthenticated, IP-counted traffic already exists: `/public/*.json` 60/h per IP (`api/middleware/rate_limit.py:233-245`, `config.py:161`), the assistant 10/h per IP via `get_optional_user` (`rate_limit.py:293-296`, `api/middleware/auth.py:172-185`), register 5/h (`rate_limit.py:261-265`). WAF: 100/300 s per IP and 6,000/300 s in total (`pyvar-cdk/stacks/edge_stack.py:105,212-234`). **[V]** `portal/privacy.html` contains no mention of "IP" (grep), so the privacy gap exists today regardless of this decision.
6. **[V]** Google sign-in creates a verified account with no form (`api/routes/auth.py:413-485`). **[A]** Whether `google_oauth_client_id` (`config.py:204`) is set in prod was not checked.

## 1. Unauthenticated trial lane

- **User:** installs, asks, gets a result. Past the allowance: "sign in for 10 a day".
- **Build:** the 386 routes each depend on `get_current_user` (`rate_limit.py:31-33`), so add one new route (`POST /api/v1/trial/{domain}/{function}`) over a whitelist of cheap inline functions, with a per-IP daily limit and a global daily budget that fails closed; no key, user row, tier or migration. `pyvar-mcp` falls back to it without a key (`client.py:68-75`, lazy client instead of `main.py:148`).
- **Abuse/cost:** bounded by the global budget; a botnet can still empty it daily. **Same weakness the owner rejected**, minus the issuance endpoint.
- **Privacy:** one more Redis IP counter of the kind in finding 5; no IP in Postgres.
- **Directory:** none. The optional key stays in `userConfig`, so the credential path and the `uvx` hold remain.
- **Runs:** 2 (API; `plugins/mcp`, since `plugins/` is not excluded, `pipeline_stack.py:1053-1062`). **Effort:** small to medium.
- **Verdict:** removes the stored credential only when paired with option 2. Not first.

## 2. MCP-native sign-in on a remote server (recommended)

**What Claude Code supports [V]:** OAuth 2.0 for HTTP servers; a server is marked as needing authentication on `401`/`403`; the user runs `/mcp` (or `claude mcp login`) and signs in in the browser; tokens "are stored securely and refreshed automatically"; discovery via RFC 9728 `/.well-known/oauth-protected-resource`, then RFC 8414; Dynamic Client Registration **and** Client ID Metadata Documents ("discovers these automatically"); random loopback callback port, with a paste-the-URL fallback.

**What the spec requires [V]** (2025-11-25): resource server serves RFC 9728 metadata, validates token audience, returns 401; authorization server implements OAuth 2.1, RFC 8414 or OIDC discovery with `code_challenge_methods_supported`, PKCE S256, exact redirect matching, refresh-token rotation for public clients; CIMD is SHOULD, DCR is MAY. The authorization server "may be hosted with the resource server or a separate entity".

**User steps:** install plugin (no prompt, no key) → first tool use shows the server needs authentication → `/mcp` → browser opens pyvar.com → "Continue with Google" → back in Claude Code. Later sessions: nothing. **[A]** One click when the browser already has a Google session; the e-mail link also works but is a mailbox round trip. It is still an account, created without a form.

**Build:**
- `api/routes/mcp_http.py`: Streamable HTTP endpoint `/mcp` reusing `plugins/mcp/pyvar_mcp/catalogue.py` and the `_invoke` dispatch, calling the existing routes as the signed-in user, so the existing per-account bucket and tier caps apply unchanged (`rate_limit.py:184-194`). No new tier.
- `api/routes/oauth.py`: `/.well-known/oauth-protected-resource`, `/.well-known/oauth-authorization-server`, `/oauth/authorize`, `/oauth/token`, optionally `/oauth/register`. Prefer CIMD or a stateless DCR (client id = signed blob of its redirect URIs) so no unauthenticated request writes to Postgres.
- `portal/authorize.html`: reuses the Google button and e-mail link (`portal/pyvar.js:313`), shows a consent line and the redirect host.
- Tokens: a 60-minute access JWT with `aud` = the `/mcp` URL and **no tier**, following the stream-token precedent; `decode_token_payload` already refuses any token with an `aud` (`auth.py:105-106`), so the REST routes keep rejecting it. Tier is read from the database as for keys (CLAUDE.md 3.5). Refresh tokens hashed in a new table (one migration), revocable from the dashboard.
- `main.py:56` route-ownership list; `config.py` flag; CLAUDE.md 3.5; tests. **[V]** CloudFront's default behaviour already forwards every path and method to the ALB (`edge_stack.py:409-415`): no CDK change.
- Plugin 0.3.0: `mcpServers: {"pyvar": {"type": "http", "url": "https://www.pyvar.com/mcp"}}`; delete `userConfig`, `env` and `uvx`. The PyPI stdio package stays for key users, CI and other hosts.

**Abuse/cost:** identical to today's free tier (10/day, 10,000 simulations per verified account); no anonymous pool to drain. New surface: authorize and token endpoints (throttle like register), localhost-redirect client impersonation (spec's known CIMD risk; a stolen token is worth 10 free calls), SSRF if CIMD documents are fetched. `tools/list` of 387 schemas on 0.5 vCPU containers needs a load check **[A]**.

**Privacy:** e-mail as today; adds refresh-token hashes and client names. No new IP processing. One paragraph in `privacy.html`.

**Directory:** removes the cause structurally for `pyvar-mcp`: no `userConfig`, no environment read, no bearer code, no launcher in the plugin folder. **[A]** That the scanner then stays silent is unverified. It does **not** clear the nine skills' holds: those are plugin-level, attached to wording, and the rule is not to touch them (`docs/plan-plugin-marketplace-status-and-submission.md:251-254`). Once they clear, their step 2 can drop all key wording.

**Runs:** 3 (API with flag off; enable; plugin manifest). **Effort:** large; it is a security-critical authorization server. **[A]** The `mcp` SDK (`mcp>=2.1.0,<3`, `plugins/mcp/pyproject.toml:17`) may ship server-side OAuth helpers; not checked. A hosted authorization server would cut effort but adds a sub-processor.

## 3. Sign-in inside the stdio `pyvar-mcp` (loopback or device code)

- **User:** first call → the server asks to open a link (**[V]** Claude Code ≥ 2.1.287 offers URL-mode elicitation to stdio servers "for a flow that finishes outside the terminal, such as sign-in") → Google click on pyvar.com → done.
- **Build:** two or three endpoints (start, poll or loopback exchange, approve under `require_session`), a dashboard confirmation, and in `pyvar-mcp` a token file in `${CLAUDE_PLUGIN_DATA}` (**[A]** a plugin cannot write the secure store). Device-code polling beats loopback: it works over SSH and in cloud sessions.
- **Versus option 2:** less server work (no discovery, PKCE or registration; medium effort, 2 runs) and it works in every MCP host. But **we** store a bearer token in a plain file, we own refresh and revocation, the `uvx` hold stays, and file → bearer → network is the pattern the earlier review rated a medium scan risk. Device-code phishing remains.
- **Verdict:** the fallback if option 2 proves too large; not a route to a clean directory listing.

## 4. Directory side

- **[V]** "Review time isn't fixed." No expedite process is documented. Channels: the plugin's portal menu, **Get help** or **Contact Anthropic** (listed first), then `directory@anthropic.com` "where replies can be delayed"; connectors use `mcp-review@anthropic.com`. The repo records only the e-mail route, unanswered (`…submission.md:236`). **[A]** The portal menu has not been tried.
- **[V]** `liquidity-risk` and `market-risk` carry identical wording with different outcomes (`…submission.md:217-222`), so rewording is a guess. Nothing in the repo speeds this up.
- **Own marketplace only:** **[V]** no review applies to a self-hosted marketplace and the skills already send users to `pyvar-mcp@pyvar-marketplace` (`:245`). Findings stop mattering there, at the cost of directory discovery. Delisting nine live 1.0.x listings gains nothing; leave them.

## 5. Other ideas

- **Trial lane on the remote server (1 + 2):** **[V]** when a server answers without a token "its tools work while you're signed out". `/mcp` could serve a small IP-limited allowance and ask for sign-in afterwards: a first result with no account and no stored credential anywhere. **[A]** Whether a mid-session 401 on a tool call reliably flips the server to "needs authentication" is untested. It keeps the drainable pool, so it is an add-on only.
- **Session-bound authorize:** if the browser already holds a pyvar session, `/oauth/authorize` shows only "Allow". Part of option 2; sessions last 60 minutes (`config.py:26`), so usually it is the Google click.
- **Local compute:** `pyvar-local` runs the same engine with no API, key, cost or personal data, but ships today as a Docker image with a CLI, not a pip package or MCP server. Large packaging work; a different product question.

## 6. Comparison

| | 1 Trial lane | 2 Remote MCP + OAuth | 3 Sign-in in stdio | 4 Own marketplace / wait |
|---|---|---|---|---|
| First result | zero steps | one Google click | one Google click | paste a key (today) |
| Credential in plugin | optional key stays | none | token file we write | key |
| New tier / migration | no / no | no / one table | no / maybe | no |
| Drainable anonymous pool | yes | no | no | no |
| New IP processing | one counter | none | none | none |
| `uvx` reviewer hold | stays | gone | stays | stays |
| Credential finding (`pyvar-mcp`) | stays | cause removed [A] | possibly worse [A] | irrelevant off-directory |
| Nine held skills | no effect | no effect now | no effect | no effect |
| Pipeline runs | 2 | 3 | 2 | 0 |
| Effort | small–medium | large | medium | none |
| Other hosts (claude.ai, Cursor) | no | yes, plus connector listing | stdio hosts only | no |

## 7. Recommendation: option 2, staged

1. **Now, no pipeline run.** Use **Contact Anthropic** in the portal on one held plugin. Put the design note in `docs/` (excluded directory). Spike locally: a FastAPI `/mcp` with OAuth against `claude mcp add --transport http` and against a plugin-declared `url`, to settle the [A] items before any commitment.
2. **Server behind a flag (run 1), enable in dev then prod (run 2).** Verify with a manually added server. No file under `plugins/` changes, so the nine stay byte-identical and nothing is re-scanned.
3. **`pyvar-mcp` 0.3.0 as an `http` plugin in our own marketplace (run 3)**, and submit `/mcp` as an MCP connector. Connector review needs a `title` and `readOnlyHint` on every tool and names of at most 64 characters **[V]**.
4. **Only if needed:** the trial lane on `/mcp`, if measured sign-in drop-off justifies a drainable pool; reword the skills when the holds clear; option 3 only if stage 1's spike fails.

Cost: three runs and the largest build here. It is the only option that leaves no credential in any plugin file, adds no tier, pool or IP data, and opens a second listing route.

## 8. Not verified

- OAuth on a plugin-declared `http` server, end to end; the mid-session 401 upgrade.
- How the directory scanner treats an `http` server with no `userConfig`; whether a change under `plugins/mcp` re-scans the nine.
- Whether the `mcp` 2.x SDK provides Streamable HTTP and authorization-server helpers that fit FastAPI here.
- Google one-click behaviour on a new `authorize` page; prod Google configuration.
- Load of 387-tool listings on the API containers; WAF interaction with MCP traffic from shared NATs.
- Whether the portal's **Contact Anthropic** was already used; no AWS, pyvar or portal state was read.
- The $0.02–0.03 per job figure and "inline on 0.5 vCPU" are taken from the brief (`pyvar-cdk/config.py:88` confirms the CPU size only).
