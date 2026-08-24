"""tests/test_disposable_email.py — unit tests for
api/middleware/disposable_email.py::is_disposable_email.

Pure-function tests: no HTTP layer, no DB/SES mocking needed — see
tests/test_auth.py for the integration-level test of the register()
rejection path this function drives.
"""

from __future__ import annotations

from unittest.mock import patch

from api.middleware.disposable_email import is_disposable_email
from config import get_settings

cfg = get_settings()


def test_known_disposable_domain_is_blocked():
    assert is_disposable_email("someone@mailinator.com") is True


def test_known_disposable_domain_is_case_insensitive():
    assert is_disposable_email("Someone@MAILINATOR.COM") is True


def test_ordinary_personal_domain_is_not_blocked():
    """gmail.com/outlook.com etc. are deliberately NOT on the vendored list —
    see the module's own docstring for why "personal-looking" isn't the
    signal this checks for."""
    assert is_disposable_email("someone@gmail.com") is False


def test_ordinary_corporate_domain_is_not_blocked():
    assert is_disposable_email("someone@fibtec.co.uk") is False


def test_operator_added_domain_via_config_is_blocked():
    with patch.object(cfg, "blocked_email_domains", ["evilcorp-spam.example"]):
        assert is_disposable_email("x@evilcorp-spam.example") is True


def test_operator_added_domain_is_case_insensitive():
    with patch.object(cfg, "blocked_email_domains", ["Evilcorp-Spam.example"]):
        assert is_disposable_email("x@evilcorp-spam.EXAMPLE") is True


def test_malformed_input_without_at_sign_is_not_blocked():
    """Defensive only — schemas/auth.py's EmailStr validation already
    guarantees a real address reaches this function in production."""
    assert is_disposable_email("not-an-email") is False
