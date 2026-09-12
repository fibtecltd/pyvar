"""
schemas/billing.py — Pydantic v2 response contracts for the Stripe Checkout +
webhook flow (item 5, Phase A — docs/plan-monetization-implementation.md).

Reasoning:
- No request body schema for POST /billing/checkout: the only input is the
  caller's own JWT (Depends(get_current_user)) — same shape as
  api/routes/var.py's GET /result/{task_id} taking no body.
- CheckoutCompleteResponse mirrors schemas/auth.py's VerifyResponse exactly
  (same three fields, same defaults) rather than reusing it directly: the
  two are semantically distinct issuance points (email verification vs.
  post-checkout token refresh) that happen to share a shape today, and
  auth.py's own docstring already treats "distinct call sites, temporarily
  identical shape" as normal (see VerifyResponse's own docstring).
"""

from __future__ import annotations

from pydantic import BaseModel


class CheckoutResponse(BaseModel):
    """Returned by POST /billing/checkout — where to redirect the browser."""

    checkout_url: str


class CheckoutCompleteResponse(BaseModel):
    """Returned by GET /billing/checkout/complete once Stripe confirms payment.

    tier reflects users.tier as read from the database at request time — the
    canonical "did this user actually get flipped to pro" answer,
    independent of and not assumed from Checkout's own payment_status alone
    (webhook processing, the actual source of truth for the tier flip, may
    not have landed yet — see api/routes/billing.py's own docstring).
    """

    access_token: str
    token_type: str = "bearer"
    tier: str = "free"
