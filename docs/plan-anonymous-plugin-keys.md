# Plan: anonymous plugin keys (proposal)

**Status: proposal, 2026-11-16; rejected by the owner the same day as not a clear win (new tier and endpoint, three pipeline runs, IP counters needing a privacy sign-off, a pool a botnet can drain). Other options: `docs/plan-plugin-keyless-access-options.md`. Nothing is built.** Written by a delegated design review (Fable) from a brief and the repository at master `7e35bbc`. Each statement about the code is tagged **[V]** (checked) or **[A]** (assumed or inferred). The author re-checked five load-bearing claims against the code: the daily cap is chosen by tier and a non-pro tier gets the free cap, the limiter fails open on a Redis outage (`api/middleware/rate_limit.py:184`, `:189`), an unknown tier counts as free for the assistant's paid quota (`:274`), key resolution rejects unverified accounts (`api/middleware/api_keys.py:173`), and checkout reads the account's e-mail (`api/routes/billing.py:216`).

**Which plugins.** The nine plugins the directory shows as held or flagged are skills: they contain no code and no key handling, so they cannot provision anything. All calls go through `pyvar-mcp`, so the bootstrap lives there and the nine stay byte-identical. This improves what a user of those plugins experiences; it does not by itself clear the directory's flag, and the skills' step 2 wording stays stale until the holds clear (`docs/plan-plugin-marketplace-status-and-submission.md` section 6.4).

**Overlap with the other proposal.** `docs/plan-academic-access.md` (academic tier) and `docs/plan-anonymous-plugin-keys.md` (anonymous plugin keys) each add a tier, change the same code (`api/middleware/auth.py` max-simulation map, `rate_limit.py` daily cap and `assistant_tier`, `api_keys.py` effective tier, `billing.py` checkout) and each names its migration `0010`. Both found that an unknown tier silently gets free-tier limits. Build them in one order, starting with a behaviour-preserving step that puts every tier's limits in one table that all of those places read, so a new tier cannot fall through to free. Not started.

## 1. Where the bootstrap lives

**Only in `pyvar-mcp`** (PyPI package and `plugins/mcp`). The nine held plugins do not change.

- [V] The domain skills hold no key and route calls through the MCP tools (`plugins/market-risk/SKILL.md:25-30`); their `plugin.json` has no `mcpServers` or `dependencies` (`plugins/market-risk/.claude-plugin/plugin.json`). Once `pyvar-mcp` works without a key, step 1 of every skill works as written.
- [V] Their step 2 still tells a user without the tools to get a key first (`SKILL.md:31-39`). That text goes stale (it is still true that a key raises quotas) and cannot be fixed until the holds clear (plan §6.4, `docs/plan-plugin-marketplace-status-and-submission.md:249-256`).
- **Not `pyvar-client`** in v1: it is a library used in scripts and CI, where self-provisioning multiplies farming and has no per-install data directory. [A]

Changes in `plugins/mcp`:

| File | Change |
|---|---|
| `.claude-plugin/plugin.json:17-25` | `pyvar_api_key` becomes `"required": false`, stays `sensitive`; description: "Optional. Leave empty to use the anonymous allowance (5 calls a day)". Keep the option declared: an undeclared `${user_config.KEY}` reference is a validation error [V, plugins-reference]. |
| `plugin.json:3,30`, `pyproject.toml:7` | 0.2.2 → **0.3.0**, pin `uvx pyvar-mcp==0.3.0`. The publish workflow fails unless tag, both versions and the pin agree [V, `.github/workflows/pyvar-mcp-publish.yml:43-63`]. |
| `pyvar_mcp/client.py:62-77` | `from_env` no longer raises without a key; treats empty or a literal `${user_config...}` as absent. |
| `pyvar_mcp/main.py:148` | The client is built at start-up today. Make key resolution **lazy, at the first tool call**, so listing tools never mints a key. |
| new `pyvar_mcp/install_token.py` | Bootstrap, storage, one retry on 401. |
| `README.md:18-21` | A "What this plugin stores and sends" section. |

Pipeline: `plugins/` is not one of the 8 excluded directories, so this PR **starts a CodePipeline run** [V, `pyvar-cdk/stacks/pipeline_stack.py:1053-1062`]. Directory: the `pyvar-mcp` listing is a frozen Console listing and 0.2.x never reaches it; users get 0.3.0 through `pyvar-marketplace` [V, plan §6.3]. [A] A commit touching only `plugins/mcp` adds no review row for the nine (§6.4 says each *changed version* adds one); §6.5 shows the portal re-reading unchanged plugins at a docs-only commit, so this is not certain.

## 2. Where the key is stored, and the directory risk

- [V] Claude Code gives each plugin `${CLAUDE_PLUGIN_DATA}` = `~/.claude/plugins/data/<id>/`, "created on first reference and kept across plugin updates", exported to stdio MCP servers, deleted on uninstall from the last place installed unless `--keep-data`. Its documented use is "installed dependencies…, generated code, and caches" (code.claude.com plugins-reference). Tokens are not mentioned either way.
- [V] Sensitive `userConfig` values go to the platform secure store. [A] No documented API lets a plugin *write* there, so a self-issued key cannot use it.
- Choice: `${CLAUDE_PLUGIN_DATA}/install.json`, mode 0600, written with `os.replace` under an `O_EXCL` lock. If `CLAUDE_PLUGIN_DATA` is unset (other MCP hosts), no bootstrap: today's error.

Honest read. The directory rule is: "Don't read a credential that is **already set in the user's environment**… and send it to a server. Ask for it through `userConfig`" [V, pre-submission checklist]. A token the plugin obtained itself is, on that text, not the user's pre-existing credential, so the rule should not apply. But:

1. The scanner is heuristic. It flagged `client.py` for env → Bearer (`docs/plan-pyvar-mcp-validation-holds.md:20-35,118`). File → Bearer → network may match the same family. [A]
2. That existing hold remains anyway, because the `PYVAR_API_KEY` path stays.
3. A network call and a file write nobody was asked about is what the security scan calls undisclosed behaviour; it must be in the README [V, checklist "Prepare for the security scan"].

Risk that 0.3.0 draws a *new* finding if resubmitted: **medium**. Risk to the nine: **low**, they are byte-identical. Wording: "anonymous installation token issued by pyvar.com", "the plugin's own data directory"; never "credential", "reads", "looks up"; file named `install.json`; the plugin reads nothing outside its data directory.

Not verified: how the scanner treats `CLAUDE_PLUGIN_DATA`; whether it reads the PyPI package or only `plugins/mcp`; what an unset optional sensitive option substitutes to (empty string assumed, hence the defensive parse); whether the enable dialog can be skipped silently.

## 3. Server-side design

**Endpoint**: `POST /api/v1/auth/anonymous-key`, no auth, returns `{key, expires_at, daily_limit, claim_url}` once. Flag `anon_keys_enabled` (default false).

**Identity**: a `users` row with `email=NULL`, `email_verified=False`, `tier="anon"`, `external_id="anon:<uuid4>"`, plus one `api_keys` row.
- [V] `users.email` is nullable and unique, `tier` is `String(16)` (`storage/models.py:108,119`); `api_keys.user_id` is NOT NULL (`models.py:185-187`), so a users row is needed.
- [V] `resolve_api_key` rejects unverified users (`api/middleware/api_keys.py:173`): add `and user.tier != "anon"`.
- [V] `_account_for` requires `email_verified` (`api/routes/auth.py:296-302`) and anonymous users never get a session JWT, so they cannot list, create or revoke keys.

**A new tier is mandatory, with explicit branches**, because an unknown tier silently gets free caps today:

| Place | Today [V] | Change |
|---|---|---|
| `api/middleware/auth.py:66-71` | unknown → 10,000 sims | add `"anon": 10_000` (must not go below `default_n_simulations`, `config.py:129-136`) |
| `api/middleware/rate_limit.py:184` | non-pro → `rate_limit_free_daily` (10) | anon: **5/day per key** and **10/day per IP or /64 across all anonymous keys** |
| `rate_limit.py:189-191` | fails open on Redis error | anon lane **fails closed** (precedent: assistant spend cap, `rate_limit.py:73`) |
| `rate_limit.py:274-284` | unknown tier → assistant "free", 40 paid questions/day (`config.py:232`) | anon key → the anonymous per-IP assistant quota |
| `api/routes/billing.py:216-238` | checkout accepts an API key, uses `row.email` | 403 for `anon` |

**Caps** (all `config.py`):

| Setting | Value |
|---|---|
| `rate_limit_anon_daily` per key | 5 |
| `rate_limit_anon_ip_daily` per IPv4 or IPv6 /64 | 10 (equal to registered free: farming keys on one address gains nothing) |
| `anon_issue_per_ip_daily` (IPv4 or /64) | 3 |
| `anon_issue_per_48_daily` | 10 |
| `anon_issue_global_daily` | 150 |
| `anon_compute_global_daily` | 500 calls, about $15/day worst case at $0.03 [A: uses the per-job figure] |
| `anon_key_expiry_days` | 30, fixed |
| `anon_pow_bits` | 0 (lever, see §4) |

Past a global cap: `429 {"detail": "The anonymous allowance is used up for today. Register free at https://www.pyvar.com#get-api-key for 10 calls a day."}`. Worst case is today's flow.

**Expiry and renewal**: 30 days. On a 401 the plugin deletes the token and bootstraps once more through the same capped endpoint. No key ever mints a key.

**Claim** (quotas rise, nothing to paste):
1. MCP tool `pyvar_link_account` calls `POST /auth/anonymous-key/claim-code` with the anonymous key: an 8-character base32 code (40 bits) in Redis, 10 minutes, single use, 3 per key per day.
2. The user opens `https://www.pyvar.com/dashboard.html?claim=CODE` and signs in as today.
3. The dashboard shows prefix and creation date, asks for confirmation, then `POST /auth/api-keys/claim {code}` under `require_session`.
4. The server sets `api_keys.user_id` to the account, `claimed_at`, extends `expires_at` to 365 days, enforces `api_key_max_active_per_user` (`auth.py:318`), and invalidates the cache (`api_keys.py:115`). The same key on disk now resolves to the account's tier within 60 s.

**§3.5 compliance**: tier is still read from the DB, never a claim [V, `api_keys.py:182`]. The key only requests a claim *code*; binding needs `require_session` [V, `auth.py:217-227`]. `/auth/register` is untouched, and the new routes never take an e-mail, so the identical-202 property holds [V, `auth.py:160-222`]. Rows are never deleted. Only the prefix is logged. A DB error is still 503.

## 4. Abuse analysis

| Attack | Impact | Mitigation | Residual |
|---|---|---|---|
| Key farming, one IP | many keys | 3 keys/day per IP; compute also capped 10/day per IP | none beyond free tier |
| IPv6 /64 rotation | bypasses per-address limits; today's register limiter and WAF key on the raw address [V `rate_limit.py:145-149`, `edge_stack.py:212-214`] | normalise to /64, plus a /48 cap | /48 holders get 10 keys/day |
| IP rotation, cloud or proxies | 5 calls per fresh IP | global caps (150 keys, 500 calls) | attacker can take the whole anonymous pool, at most $15/day |
| Free-tier quota bypass | more than 10/day without e-mail | per-IP 10/day equals the free cap | same as registering throwaway mailboxes today |
| Botnet draining the compute budget | cost, or denial to anonymous users | global budget fails closed; registered tiers unaffected | **anonymous lane can be denied daily** (accepted: falls back to registering) |
| Issuance endpoint as DoS target | DB writes, pool of 5+5 | limiter before any DB work; WAF 100 per 300 s per IP; global cap bounds writes to 150/day; `anon_pow_bits` | volumetric load is WAF's job, as for every route |
| Analytics poisoning | inflated adoption | `api_usage.tier="anon"`; verified-account counts read `email_verified` (`api/routes/internal.py:115`) | anonymous counts are untrusted by design |
| Leaked embedded secret | n/a | **embed nothing**; the client is open source | none |
| Replay or stolen `install.json` | bearer reuse | TLS, 0600, 5/day, 30 days | low |
| Privacy | an IP is personal data (UK GDPR); the policy promises no user identifier in usage records [V `docs/plan-durable-api-keys.md:62`] | no IP in Postgres; Redis counters only, keyed by HMAC(prefix, daily salt), 24 h TTL; legitimate-interest note; update `portal/privacy.html` | PECR device-storage exemption assumed, needs a legal check [A] |
| Claim abuse (device-code phishing) | attacker's key bound to a victim's, possibly Pro, account | confirmation screen, visible and revocable in the key list, 5-key cap, single-use 10-minute code | **medium**: social engineering remains |
| Claim-code guessing | hijack a pending claim | 40 bits, 10 minutes, existing per-IP failure throttle | negligible |

Verdicts: per-IP and per-/64 caps **yes** (the core). Global budget, fail-closed, clear error **yes** (the real cost bound). Proof-of-work **built, off**: 18 bits is about 0.2 s in Python and trivial for an attacker; useful only as a surge lever. Installation-bound keys **no**: any binding secret sits in the same file. Short expiry with silent renewal **yes** (30 days, re-issue). Attestation **not realistic** for an open-source CLI.

## 5. Alternatives

| Option | Verdict |
|---|---|
| (a) Shared public demo key | **Reject**: one bucket, first abuser denies everyone, cannot revoke per abuser, the key is a published secret. |
| (b) OAuth device flow | Strongest identity, but still a registration. **Use its shape for the claim step only.** |
| (c) Anonymous per-install keys | **Recommend**, with caps that make the worst case equal to today. |
| (d) Better error only | **Do regardless**, as the fail-closed fallback text. Alone it misses the goal. |

Recommendation: **(c) + (b)-shaped claim + (d)**: zero-touch first result, bounded spend, failure degrades to the current flow. Resale of a 5-call key is not a concern.

## 6. Failure modes and UX

- **First call**: one extra POST, under 1 s [A]; lazy, so none at start-up.
- **Offline**: tool error "cannot reach pyvar.com"; nothing written.
- **Issuance refused**: the register message, plus "or set a key in the plugin's settings".
- **Expired or revoked mid-session**: one silent re-issue and retry. If the old key had been claimed, say once that calls now use the anonymous allowance.
- **Two machines**: two identities; behind one NAT they share 10/day and 3 keys/day. Offices hit this first.
- **Uninstall and reinstall**: data directory deleted, new key, counted against the IP cap.
- **CI**: if `CI` is set, never bootstrap; require `PYVAR_API_KEY`.

## 7. Implementation plan

| # | PR | Files | Pipeline run? |
|---|---|---|---|
| 1 | `docs/` design note | `docs/plan-anonymous-keys.md` | No |
| 2 | `feat(api)`, flag off | `config.py`, `api/middleware/{auth,api_keys,rate_limit}.py`, new `api/middleware/anon_keys.py`, `api/routes/{auth,billing}.py`, `schemas/auth.py`, `storage/models.py`, `migrations/versions/0010_anon_keys.py`, `portal/{privacy,terms,dashboard}.html`, `CLAUDE.md` §3.5, tests | **Yes** |
| 3 | `feat(mcp)` 0.3.0, then tag `pyvar-mcp-v0.3.0` | §1 files, `plugins/mcp/tests/` | **Yes** (the tag only publishes to PyPI [A]) |
| 4 | Enable in dev, then prod | env flag in `pyvar-cdk` config | **Yes** each |

Merge 2 before 3: 0.3.0 against an API without the endpoint just shows the register error.

- **Migration 0010** (new file, sync driver, CLAUDE.md §3.3): nullable `api_keys.origin String(16)` and `api_keys.claimed_at`. No change to `users`.
- **Kill switch**: `anon_keys_enabled` (deploy) plus a Redis override `pyvar:anon:disabled`, set by a script in `scripts/` (excluded directory; precedent `scripts/toggle_kill_switch.sh`, `edge_stack.py:46-48`). Both stop issuance; the override also makes anonymous keys answer 429.
- **Tests** (CLAUDE.md §5, moto and fake Redis only): 201 on issue; 404 with the flag off; 429 on per-IP, /64, /48 and global caps; fail-closed on Redis error; anon gets 5/day and 403 above 10,000 sims; anon key refused by key-management routes and checkout; claim needs a session, is single use, respects the 5-key cap and moves the tier; register still returns the identical 202; a DB error is 503. In `plugins/mcp/tests`: lazy bootstrap, 0600, `CI` refusal, one retry on 401, configured key wins.

## 8. Open decisions (recommended default)

1. Anonymous caps: **5/key, 10/IP, 500 global calls, 150 keys a day**.
2. Expiry: **30 days, silent re-issue**.
3. Bootstrap outside Claude Code (no `CLAUDE_PLUGIN_DATA`): **no**.
4. `pyvar-client` self-provisioning: **no**.
5. Proof-of-work: **built, off**.
6. Claim flow in v1: **yes** (otherwise upgrading means pasting a key again).
7. May claimed keys inherit Pro: **yes, with the confirmation screen**; alternative is free-only.
8. Resubmit `pyvar-mcp` 0.3.0 to the directory: **not until the nine holds clear**.
9. Privacy policy and legitimate-interest note before enabling in prod: **required, owner sign-off**.
