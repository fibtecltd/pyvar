# Plan: show which account is signed in on the dashboard (issue #454)

**Status: requested by the owner on 2026-11-25 (issue #454); not built.** Written after the prod Stripe test of 2026-11-24, where a
person with two addresses could not tell which account a stored session belonged to. **[V]** means read at the file cited.

## 1. The problem

The dashboard (`portal/pyvar.js`, the dashboard branch) shows the keys and the plan, not the address. A person who uses more
than one address (testing, support) cannot tell which account a session, a key or a purchase belongs to, and the only way to
find out is to sign out and try again.

## 2. What the code does today

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
