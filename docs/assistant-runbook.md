# Typed assistant: runbook

For the person who runs the typed assistant (`POST /api/v1/assistant/ask`) once it is on. The design is
`docs/assistant-plan-implementation.md`; the rules are `CLAUDE.md` 3.7 and 3.8. **Owner and only responder for now: the
owner** (question B3 of 2026-11-26 was left open and (a), the owner alone, is assumed until the owner names a second
recipient; the alarms below go to the shared alerts topic, whose mailbox must be read every day while the route is
open). **Not verified:** every command below was checked against the code and its tests, none
has been run against a live environment.

## 1. The switches, from the broadest to the narrowest

| What | How you change it | Needs a deploy? | Effect |
|---|---|---|---|
| The route itself | CDK flag `assistant_typed_enabled` (needs `assistant_enabled` too) | yes | off: 503 `assistant_disabled` for everyone |
| The watchdog | CDK flag `assistant_watchdog_enabled` (must be on wherever typed is) | yes | audits, pins, degrade flag |
| Who may ask | CDK flag `assistant_allowlist_enabled` | yes | on: only accounts in the set (section 3); off: everyone the other switches admit |
| The set of accounts | `scripts/ops/assistant-allow.sh` (section 3) | no | per account, at once |
| The kill switch | Redis key `pyvar:assistant:kill` (section 4) | no | any value: 503 `assistant_disabled` for everyone, at once |
| An audience, by quota | `assistant_quota_anon_per_hour`, `assistant_quota_<free\|pro\|enterprise>_daily` set to 0 | yes | 429 for that audience, no model call, nobody else affected |
| The day's spend | `assistant_daily_budget_usd` (5.0) | yes | at the cap: 503 `assistant_budget` until 00:00 UTC |

## 2. Opening the route in stages (decision E7, 2026-11-26)

1. **Dev run** (decision D): one run, $2 cap, about 60 questions, with drills for the kill switch, the spend cap, the
   quota and planted fake keys. Pass bar: no planted key echoed; the kill switch and the cap each refuse the next
   request with no model call; p95 under 12 s; the audit flag rate no worse than the measured 3.4%, and a person
   reads every flagged answer.
2. **Prod allowlist for about two weeks**: typed, watchdog and allowlist on; the owner's own accounts first, then a
   few more. Anonymous visitors and enterprise stay out.
3. **All signed-in free and Pro accounts**: turn `assistant_allowlist_enabled` off (a deploy).
4. **Anonymous visitors**, then **enterprise** (enterprise answers are not audited until the synchronous reader is built).

Move to the next step only when, over the step: no pin is unresolved, the day's spend peaked below 50% of the cap, no
scrub incident was found, and every alarm that fired is explained. Each step is the owner's decision.

## 3. The allowlist

The set holds account ids (`users.external_id`), never addresses. Reading it fails closed: if it cannot be read, nobody
is let in (503 `assistant_unavailable`, log line `assistant_store_unavailable`).

```
scripts/ops/assistant-allow.sh --env prod list
scripts/ops/assistant-allow.sh --env prod allow  --email <address>            # dry run
scripts/ops/assistant-allow.sh --env prod allow  --email <address> --apply
scripts/ops/assistant-allow.sh --env prod remove --email <address> --apply
scripts/ops/assistant-allow.sh --env prod clear --apply                        # every account refused at once
```

The wrapper asks you to type `prod`, masks the address, and the script says "allowed" or "removed" only after a second
call confirms it. `list` says whether the allowlist is ON in that environment: the set does nothing where
`assistant_allowlist_enabled` is off. Where Redis can be reached the same set is `SADD`, `SREM`, `SMEMBERS` and `DEL` on
`pyvar:assistant:allow`.

## 4. Stopping it, fastest first

1. **While the allowlist is on:** `scripts/ops/assistant-allow.sh --env prod clear --apply`. Needs no Redis access.
2. **The kill switch:** `SET pyvar:assistant:kill 1` (any value) on the cache the API uses; `DEL` turns it back on.
   It needs a Redis client inside the VPC. **Not verified here: which route you use** (for example `aws ecs
   execute-command` into an API task, if exec is enabled); settle that before the first prod day.
3. **A deploy** with `assistant_typed_enabled` off (or a quota of 0 for one audience).

## 5. The eight alarms

All are `pyvar-<env>-assistant-<name>`, send to the shared alerts topic, and treat missing data as OK, so they are quiet
until the route is on.

| Alarm | Fires on | First thing to look at |
|---|---|---|
| `client-unavailable` | 1 `assistant_client_unavailable` in 5 min | the secret `pyvar/<env>/anthropic-api-key` (section 7): missing, empty or unreadable; every question is a 503 |
| `store-unavailable` | 1 `assistant_store_unavailable` in 5 min | Redis: the spend, the kill switch or the allowlist could not be read; the route fails closed, so this is an outage of the box |
| `ask-failed` | 3 `assistant_ask_failed` in 5 min | the API log for the stack trace (no question or answer text is in it) |
| `writer-degraded` | 1 `assistant_writer_degraded` in 5 min | the watchdog degraded a writer: its answers are fixed text with 10% probe traffic; see section 6 |
| `watchdog-errors` | 5 `assistant_watchdog_error` in 5 min | the audit judge or its Redis state; answers are unaffected (it fails open) |
| `spend-not-recorded` | 3 `assistant_spend_not_recorded` in 5 min | Redis writes failing; the cap may be under-counting, so check the Anthropic console |
| `budget-high` | 1 `assistant_budget_high` in 5 min | the day's spend passed 80% of the cap; expect 503 `assistant_budget` before midnight UTC |
| `pinned` | 1 `assistant_pinned` in 60 min | a function's live answers kept being flagged and it now serves fixed text for 7 days (doubling); section 6 |

## 6. The watchdog, by hand (no deploy)

- Unpin a function: `redis-cli DEL pyvar:assistant:wd:fn:<bank_version>:<function>:pin` (also `DEL ...:level` to forget
  it was ever pinned).
- Lift a degrade: `redis-cli DEL pyvar:assistant:wd:degrade:<writer>`.
- The kill switch stops everything either way. The watchdog stores counts, function names, writer families and booleans
  only; never a question, an answer or an account.

## 7. The Anthropic key

One dedicated key per environment, in its own Anthropic workspace with a spend limit set on Anthropic's side (decision
B1: about $20 a month for dev and about $160 for prod, just above the app's own $5-a-day cap, so the app's cap acts
first). Store it as the bare value in the secret `pyvar/<env>/anthropic-api-key` (`put-secret-value`). The API reads it at
call time and caches it for 60 seconds, so a rotation needs no deploy and takes effect within about a minute; a failed
read is never a stale or empty key. The key is never an ECS `secrets={}` entry, so a missing secret cannot stop a task
launching.
