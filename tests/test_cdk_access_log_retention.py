"""tests/test_cdk_access_log_retention.py — CloudFront's access logs expire, and the privacy policy says when.

Reasoning:
- `enable_logging=True` on the distribution (pyvar-cdk/stacks/edge_stack.py) makes CDK create an S3 bucket for
  CloudFront's standard access logs. Those logs hold each request's IP address and URL (query string included).
  Before 2026-11-20 the bucket had no lifecycle rule, so they were kept forever while the privacy policy said
  nothing about IP addresses (docs/plan-education-tier.md section 12).
- The fix adds an expiry rule to that same bucket (looked up as the distribution's "LoggingBucket" child; a
  synth against master showed only that bucket's LifecycleConfiguration changing, no replacement). The number of
  days is one constant, `ACCESS_LOG_RETENTION_DAYS`, and the policy states it. This test pins the two together so
  that changing the rule without the page (or the page without the rule) fails here.
- Same approach as tests/test_cdk_education_flag.py: the CDK code is read, not run, so aws-cdk-lib is not needed
  in the application test environment. The real check, a synth of dev, staging and prod, is in the PR description.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EDGE = ROOT / "pyvar-cdk" / "stacks" / "edge_stack.py"
PRIVACY = ROOT / "portal" / "privacy.html"


def _edge_source() -> str:
    if not EDGE.exists():
        pytest.skip(f"source file not found (cannot audit): {EDGE}")
    return EDGE.read_text(encoding="utf-8")


def _days() -> int:
    match = re.search(r"^ACCESS_LOG_RETENTION_DAYS = (\d+)$", _edge_source(), re.M)
    assert match, "edge_stack.py has no ACCESS_LOG_RETENTION_DAYS constant"
    return int(match.group(1))


def test_the_access_log_bucket_gets_an_expiry_rule_from_the_constant() -> None:
    source = _edge_source()
    assert (
        "enable_logging=True" in source
    ), "the distribution no longer logs: update this test and the policy"
    assert 'try_find_child("LoggingBucket")' in source
    assert (
        "isinstance(log_bucket, s3.Bucket)" in source and "raise RuntimeError(" in source
    ), "a CDK release that renames the bucket must fail the synth, not drop the rule"
    rule = re.search(r"log_bucket\.add_lifecycle_rule\((.*?)\n\s*\)", source, re.S)
    assert rule, "no lifecycle rule is added to the log bucket"
    assert "expiration=Duration.days(ACCESS_LOG_RETENTION_DAYS)" in rule.group(1)
    assert "enabled=True" in rule.group(1)


def test_the_retention_is_bounded_and_not_shorter_than_the_investigations_need() -> None:
    # a quarterly look-back (docs/seo-crawl-investigation.md read 46 days) and never "forever"
    assert 46 < _days() <= 400


def test_the_privacy_policy_states_the_same_number_of_days() -> None:
    html = PRIVACY.read_text(encoding="utf-8")
    assert (
        f"keeps access logs, which include the IP address and the address requested, for {_days()} days"
        in html
    )
    assert "Amazon CloudFront" in html
