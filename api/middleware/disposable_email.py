"""
api/middleware/disposable_email.py — disposable/throwaway email domain check.

Reasoning:
- Scope is deliberately narrow: this blocks known temp-mail/throwaway
  services (mailinator.com, 10minutemail.com, etc.), not "personal-looking"
  domains like gmail.com or outlook.com. Blocking the latter would exclude
  the individual quant developers and hobbyist contributors this project's
  README and launch plan explicitly target, on a signal (domain "looks
  personal") that doesn't actually establish whether an account is real or
  legitimate. See docs/pyvar_release_plan.md for the project's stated
  audience.
- Static, vendored list rather than a live network call (an MX-record
  lookup or a third-party verification API) — registration must not gain a
  new external dependency or added latency, and disposable-domain lists
  change slowly enough that a redeploy-to-update tradeoff is acceptable.
  Not exhaustive by design; cfg.blocked_email_domains (config.py) lets an
  operator add domains without a code change.
- Domain match is exact + case-insensitive on the part after the last "@"
  — no subdomain/wildcard logic, since disposable-mail providers are
  identified by their exact registered domain, not a suffix pattern that
  could false-positive on an unrelated domain sharing a suffix.
"""

from __future__ import annotations

from config import get_settings

# Not exhaustive — a representative set of long-standing, well-known
# disposable/temp-mail providers. Extend via cfg.blocked_email_domains
# rather than editing this set for one-off additions.
DISPOSABLE_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "mailinator.com",
        "guerrillamail.com",
        "guerrillamail.info",
        "10minutemail.com",
        "10minutemail.net",
        "tempmail.com",
        "temp-mail.org",
        "throwawaymail.com",
        "yopmail.com",
        "getnada.com",
        "trashmail.com",
        "sharklasers.com",
        "dispostable.com",
        "fakeinbox.com",
        "maildrop.cc",
        "mintemail.com",
        "mailnesia.com",
        "spamgourmet.com",
        "moakt.com",
        "emailondeck.com",
    }
)


def is_disposable_email(email: str) -> bool:
    """True if `email`'s domain is a known disposable/throwaway provider.

    Args:
        email: A full email address. Case doesn't matter — domain is
            lowercased before comparison.

    Returns:
        bool: True if the domain is in the vendored list or in
            cfg.blocked_email_domains.
    """
    _local, _, domain = email.rpartition("@")
    domain = domain.strip().lower()
    if not domain:
        return False

    cfg = get_settings()
    blocked_extra = {d.strip().lower() for d in cfg.blocked_email_domains}
    return domain in DISPOSABLE_EMAIL_DOMAINS or domain in blocked_extra
