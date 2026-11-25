# Plan: show which account is signed in on the dashboard (issue #454)

**Status: built. Requested by the owner on 2026-11-25 (issue #454); merged the same day in PR #457 (merge commit `07a7a3d`).**
Written after the prod Stripe test of 2026-11-24, where a person with two addresses could not tell which account a stored
session belonged to. Sections 1 and 2 describe the code as it was before that PR; section 9 records what was built and where
it differs from this plan. **[V]** means read at the file cited.

## 1. The problem

The dashboard (`portal/pyvar.js`, the dashboard branch) shows the keys and the plan, not the address. A person who uses more
than one address (testing, support) cannot tell which account a session, a key or a purchase belongs to, and the only way to
find out is to sign out and try again.

## 2. What the code did before PR #457

- The session token carries `sub` (the account's `external_id`) and `tier`, nothing else (`api/middleware/auth.py`,
  `create_access_token`). [V]
- No route returns the address to a session: `api/routes/auth.py` has register, verify, the Google sign-in and the three
  api-keys routes. [V]
- The Google sign-in finds an existing account by its address and only creates one when there is none, so one address is one
  account whichever way it signs in. Two accounts therefore means two addresses. [V]
- The page takes the stored token from localStorage `pyvar_jwt`. [V]

## 3. Decision: a read-only route (recommended)

| Option | Result |
| --- | --- |
| **`GET /api/v1/auth/me`**, session token only, answering `{email, tier}` | Chosen. The token does not change, nothing new is stored. |
| Put the address in the token | Not chosen: it would sit in every token, and the page reads that token into view, so it would show up in screenshots and pasted tokens. |
| Return it from `/auth/verify` only | Not chosen: it does not cover the return from Stripe (`checkout/complete`) or a reload with a stored token. |

## 4. What to build

1. `GET /api/v1/auth/me` in `api/routes/auth.py`, behind `require_session` (`api/middleware/auth.py`, the dependency the
   api-keys routes use). It reads the account's address and tier from the database for the token's `sub`; the tier goes
   through `effective_tier()` (`api/tiers.py`), not from the token claim. The response model goes in `schemas/auth.py`. An
   erased account has `users.email` NULL (CLAUDE.md 3.5): answer without an address, never a 500.
2. `portal/pyvar.js`, dashboard: once the session is known, call the route with the session token and show
   "Signed in as <address>" in the dashboard card, with `textContent` or the existing `_escapeHtml`, never raw HTML. If the
   call fails or there is no address, show nothing and leave the rest of the dashboard working. The address is not added to
   the token, to localStorage or to any other page.

## 5. Rules

- The address goes in no log line, metric, exception text or token claim; the response is not logged.
- An API key, a stream token, a trial ticket and an admin token must all be refused by the route (`require_session` does it:
  prove it, as `tests/test_api_keys.py` and `tests/test_trial_ticket.py` do, and add the new path to the admin-token test
  in `tests/test_education_admin.py`).
- No new stored data (a person sees their own address), so no privacy-page change is expected; check the page's wording on
  what the dashboard shows and say in the PR that nothing needed changing, or change it in the same PR.
- Tests use example.com style addresses. No real or tester address anywhere in the repo.

## 6. Tests

401 without a credential; 200 with a session token and the right address and tier; the four other credential types refused;
an erased account; a log-capture test showing the address appears in no record; the existing api-keys tests still pass.

## 7. Not in scope

A sign-out button, other dashboard changes, anything in billing or the allow list.

## 8. Deploy

The change touches `api/` and `portal/`, outside the eight directories CLAUDE.md 8.1 excludes, so merging it starts a real
CodePipeline run: say so in the PR and merge when the owner says. Back out by reverting the PR; the route is read-only and adds
no data.

## 9. As built (PR #457, merged 2026-11-25)

Built as sections 4 to 7 say. Where the build chose, or added something the plan did not name:

- **The route.** `whoami` in `api/routes/auth.py`; the response model is `AccountInfo` in `schemas/auth.py`, with `email` a plain
  `str | None` (not `EmailStr`, so a stored address can never turn the answer into a 500) and `tier`. An erased account is
  answered with `email: null`; that is why the route does not use `_account_for`, which refuses an unverified account with a 403.
  An account that does not exist gets the same 403 as the api-keys routes.
- **Added, not in the plan: `Cache-Control: no-store`** on the response, because it is about one person. The edge cache policy
  already has a 0 s default TTL and keys on `Authorization`, so this is belt and braces. It was kept.
- **The page.** `_signedInAs` and `_accountLine` in `portal/pyvar.js`. The address is drawn as a string child through the
  existing `_h` builder (never parsed as HTML), where the plan named `textContent` or `_escapeHtml`. `renderKeyManager` asks for
  it in parallel with the key list, and again each time the card is redrawn (after a key is created or revoked): one small extra
  GET, and the page holds no state. If the call fails or there is no address, nothing is shown.
- **Tier.** The guard test `test_the_three_session_mints_read_the_tier_through_effective_tier` (`tests/test_education_admin.py`)
  now names the three session mints and `whoami`, and counts four `effective_tier(` sites; a route that read the tier from the
  token claim would fail it.
- **Tests.** `tests/test_auth_me.py` (the route, on an in-memory database); `tests/test_dashboard_account_line.py` (the real
  dashboard code under node, with a fake DOM that throws if `innerHTML` is touched and a `localStorage` that throws on any use);
  and the new path in the admin-token matrix of `tests/test_education_admin.py`.
- **Privacy page.** Read and not changed: nothing new is stored, and a person is shown their own address.
- **Also fixed in the same PR, not in the plan.** On a screen narrower than about 550 px the dashboard card was wider than the
  screen, with or without the new line (a flex item will not shrink below its content, and the seven-column keys table needs
  about 450 px), and a long address with no break opportunity ran past the card at every width. Fixed in
  `portal/dashboard.html` and `portal/pyvar.js`; the rules are pinned by `tests/test_dashboard_phone_width.py`.
- **Not seen on a deployed environment (as of 2026-11-25).** It was checked in Chromium against canned API answers, not against
  a real deployment. After the dev deploy: signed in on dev, the dashboard shows "Signed in as <address>" under "Your API keys".
  Prod follows its own approval.
