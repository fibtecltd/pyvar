# 13 Plugins Published, and Three Real Upgrades Shipped Behind Them

*A follow-up to "14 Plugins, One API" — the marketplace listing finally went live, and it wasn't the only thing that moved.*

> **Draft status:** not yet published. Every fact below is checked against
> this repository at drafting time (`git log`, `.claude-plugin/marketplace.json`,
> `config.py`, `docker-compose.yml`, `api/routes/auth.py`, `api/routes/var.py`) —
> see **Sources** at the end. Needs review before it goes anywhere.

---

Two weeks ago, pyvar's 14-plugin Claude Code marketplace submission was stuck. Anthropic's new developer portal rejected every one of the 14 `marketplace.json` entries with `EXTERNAL_SOURCE_NOT_ALLOWED` — a GitHub-object-form `source` field the old submission path accepted, the new one doesn't. That's now fixed, and the result is visible, not just claimed:

| | Then | Now |
|---|---|---|
| Marketplace status | 14/14 blocked, `EXTERNAL_SOURCE_NOT_ALLOWED` | **13/14 `Published`**, live on the directory |
| `pyvar-mcp` (the MCP server) | Blocked alongside the rest | `In review` — the one plugin that executes code, reviewed last on purpose |
| Docker build CI check | Flaking red on `public.ecr.aws` rate limits (confirmed on PRs #370, #371, #375, #376 itself) | Green — CI-only builds now pull from `docker.io`, production untouched |

That table alone would be worth a short post. But the same two weeks also shipped three pieces of real engineering — not configuration fixes, actual new capability — and they deserve more than a changelog line each.

## 1. Results pushed, not polled

Every `pyvar` job used to work the same way: `POST /var/compute` to submit, then `GET /var/result/{task_id}` in a loop until the status flips from `PENDING` to `SUCCESS`. It works, but it means every client either over-polls (wasted requests) or under-polls (a result sits ready for seconds before anyone asks for it).

`WS /api/v1/var/stream/{task_id}` is now the alternative: open one WebSocket connection, and the result is pushed the moment the Celery task finishes — no polling loop on the client at all. The polling endpoint didn't go anywhere; this is additive.

The engineering decision worth calling out is what the new route refuses to trust. Redis Pub/Sub has no persistence and no replay — if a message is missed, it's gone. So the stream route never relies on the push alone:

```python
# api/routes/var.py — every wake-up, pushed or timed out,
# re-reads the authoritative Celery state. A lost Pub/Sub
# message costs one poll interval (2s), never a hung connection.
```

Worst case, a dropped Pub/Sub message degrades the WebSocket back into the same poll cadence the old endpoint always had — bounded by `var_stream_max_wait_seconds` (900s). Best case, the client finds out the instant the job completes. There's no failure mode where the new path is worse than the one it sits beside.

One more small fix rode along for free: WebSocket handshakes can't set a custom `Authorization` header from a browser, so `api/middleware/auth.py` now has a single `decode_token_payload()` that both the header-based poll route and the query-param-based stream route call — one validation path instead of two that could quietly drift apart.

**Verified:** 101 tests passing across the affected modules, including 5 new WebSocket tests (immediate success, immediate failure, missing token, invalid token, the Pub/Sub-subscribe-and-poll loop itself).

## 2. `docker compose up` is now the entire setup

`pyvar-local/` — the engine-only Docker package — already existed. What didn't exist was a way to stand up the *full* application (API + worker + Redis + Postgres) in one command, with nothing external required.

`pyvar-full/` closes that gap, built on the same production Dockerfile the hosted `pyvar-prod-api` image already uses — zero changes needed there, because it already does a self-contained `COPY . .` with no bind-mount dependency. The new work was entirely in the compose file:

| | Repo-root `docker-compose.yml` | `pyvar-full/docker-compose.yml` |
|---|---|---|
| Bind mounts | Yes (live source mounted in) | None — the image is the artifact |
| External prerequisite | `docker network create pyvar_net`, shared with a sibling repo's compose file | None |
| Database migration | Manual, separate step | One-shot `migrate` service, runs automatically |
| Who it's for | Active development on pyvar itself | Anyone evaluating the full stack |

The billing module question — ship `api/routes/billing.py` or strip it out of the distribution build — resolved itself on inspection rather than needing a decision: `_require_billing_configured()` already returns a clean 503 on every billing route whenever Stripe keys are unset, and `local-eval.env` leaves them blank by default. Nothing to strip, nothing to configure, nothing to get wrong.

## 3. A second way in: Google Sign-In

pyvar's only account path used to be one way, with a wait built into it: `POST /auth/register` with an email, then an SES verification link, then click it to get a JWT. `POST /auth/google` is now a second, faster path to the exact same end state — not a replacement, an addition.

The interesting part isn't the button — it's what pyvar *didn't* have to build to add it. tengrade's own social-login feature (R7, PRs #178/#179) runs through AWS Cognito, a Hosted UI OAuth2 authorization-code flow, and a client secret in Secrets Manager. pyvar has none of that machinery, and Google Identity Services doesn't require it: the frontend gets a signed ID token directly, and the backend verifies it with `google-auth`'s own verifier — signature, issuer, audience, expiry — no authorization-code exchange, no client secret, anywhere.

```python
# api/routes/auth.py — the whole trust boundary is one library call
claims = google_id_token.verify_oauth2_token(
    raw_token, google_requests.Request(), cfg.google_oauth_client_id
)
```

Account linking reused an existing constraint instead of inventing new logic: `User.email` already had `unique=True`, so "look up by email, else create" *is* the linking mechanism — no new table, no new join. And `User.external_id` — a column that had sat documented since migration `0002` as "external identity provider ID" with nothing populating it but a placeholder UUID — finally gets a real value: `google:{sub}`.

One architectural difference from tengrade mattered enough to call out explicitly: tengrade blocks free-mail domains on new signups and only allows Google/Apple sign-in to *link* an existing account, because its domain-vetting rule would otherwise conflict with it. pyvar has no such rule — the portal's own copy already says "no password, no credit card" — so here Google sign-in is a genuine new-signup path, not a linking-only one.

| | Email registration | Google sign-in |
|---|---|---|
| Steps to a usable JWT | Submit form → check inbox → click link | Click button |
| Round trip | SES send + click | None |
| New account created | Immediately, unverified | Immediately, verified (Google's `email_verified` claim is trusted) |
| Infra required | SES (already existed) | One Client ID — not a secret, same posture as an unset `STRIPE_SECRET_KEY`: the route 503s cleanly until it's configured |

**Verified:** 121 tests passing, including 6 new sign-in tests (new-user creation, linking an existing verified user, verifying a previously-unverified one, invalid token, unverified email claim, the clean 503 when unconfigured) and 2 new tests for the config endpoint the button depends on.

Registering the real Google Cloud OAuth app and wiring the Client ID into the ECS task environment are the two steps left — both infrastructure, not code, and deliberately out of scope here, the same way tengrade's own R7 slice shipped its application code before the OAuth app existed and tracked the registration as a separate follow-up.

## The thread running through all three

None of this shipped as a burst of unrelated fixes. The marketplace fix, the streaming feature, and the CI reliability fix landed in the *same* pull request (#376) for a concrete reason: `Dockerfile` is a root-level file, not covered by the CodePipeline trigger-exclusion list in this repo's own `CLAUDE.md`, so changing it on its own would start a real pipeline execution. The streaming feature already touched `api/` and `tasks/`, which triggers a pipeline run regardless — so bundling the Docker fix in cost zero *additional* pipeline runs instead of two. That's not a coincidence; it's the same cost-discipline this project applies to CodeBuild image choices being applied to its own CI workflow.

And every one of these three changes was verified the same way: the exact pinned lint/format tool versions CI uses (`ruff==0.15.22`, not whatever `pip install` floats to — a drift trap the repo's own CI config comments explicitly flag), the relevant test files run locally before pushing, and every sandbox limitation (no Docker daemon, no live browser) disclosed rather than hidden behind an unverified "should work." It's the same "don't trust it, run it and check" discipline that caught a 79%-understated Solvency II capital formula before launch — just pointed at infrastructure and auth instead of a regulatory calculation this time.

## Try it

```
/plugin marketplace add fibtecltd/pyvar
/plugin install pyvar-market-risk@pyvar-marketplace   # any of the 13 published skills
/plugin install pyvar-mcp@pyvar-marketplace            # pending review, installs today regardless
```

The marketplace add command works right now against the live repository no matter where Anthropic's review lands — it's a direct GitHub-source install, not routed through their review process. And `pyvar-full/` is a `docker compose up` away from a complete local instance, Google button included once a Client ID is set.

---

## Sources

- [`.claude-plugin/marketplace.json`](https://github.com/fibtecltd/pyvar/blob/master/.claude-plugin/marketplace.json) — 14-plugin manifest, current publish status referenced from Anthropic's developer portal.
- [PR #376](https://github.com/fibtecltd/pyvar/pull/376) — marketplace source-path fix, `WS /api/v1/var/stream/{task_id}`, CI Docker build-arg fix, all three bundled with the reasoning above.
- [`api/routes/var.py`](https://github.com/fibtecltd/pyvar/blob/master/api/routes/var.py), [`tasks/var_task.py`](https://github.com/fibtecltd/pyvar/blob/master/tasks/var_task.py) — streaming push implementation, `_publish_job_event`, `_build_job_result_response`.
- [`config.py`](https://github.com/fibtecltd/pyvar/blob/master/config.py) — `var_stream_poll_interval_seconds`, `var_stream_max_wait_seconds`, `google_oauth_client_id`.
- [PR #375](https://github.com/fibtecltd/pyvar/pull/375) — `pyvar-full/`, the all-in-one Docker distribution.
- [`pyvar-full/docker-compose.yml`](https://github.com/fibtecltd/pyvar/blob/master/pyvar-full/docker-compose.yml) — the one-command setup described above.
- [PR #377](https://github.com/fibtecltd/pyvar/pull/377) — Google sign-in, adapted from tengrade's R7 design.
- [`api/routes/auth.py`](https://github.com/fibtecltd/pyvar/blob/master/api/routes/auth.py), [`api/routes/public_data.py`](https://github.com/fibtecltd/pyvar/blob/master/api/routes/public_data.py) — `POST /auth/google`, `GET /public/config`.
- [`docs/publications/pyvar-plugins-medium-article.md`](https://github.com/fibtecltd/pyvar/blob/master/docs/publications/pyvar-plugins-medium-article.md) — the original 14-plugin piece this one follows up on.
- [`docs/publications/pyvar-buildstory-medium-article.md`](https://github.com/fibtecltd/pyvar/blob/master/docs/publications/pyvar-buildstory-medium-article.md) — the Solvency II calibration this piece draws the verification-discipline parallel to.
