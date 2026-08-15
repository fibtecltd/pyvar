"""
tests/test_var_scale_kickstart.py — regression coverage for task #38: the
scale-from-zero kickstart metric api/routes/var.py publishes on job
submission must never touch real AWS in tests, and must never raise
(the actual /var/compute response must never fail or slow down because of
this best-effort signal).

Reasoning:
- Mirrors tests/test_observability.py's pattern for _resolve_sentry_dsn():
  patches api.routes.var.cfg directly (the already-instantiated module-level
  Settings object), not config.get_settings() (the latter is @lru_cache'd,
  so re-invoking it wouldn't reliably produce a new instance
  api/routes/var.py would actually see).
- Same ecs_container_metadata_uri_v4 gate as observability/setup.py's
  _resolve_sentry_dsn() — the first test here proves that gate actually
  works for this function specifically, not just that boto3 happens to be
  unmocked (a boto3 failure would also be silently swallowed, masking a
  broken gate).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from api.routes.var import _emit_scale_kickstart_metric, cfg


def test_emit_scale_kickstart_metric_noop_outside_ecs():
    """Rule 3 (CLAUDE.md/tests): never touch real AWS services in tests. Local
    dev and CI's test job never have ecs_container_metadata_uri_v4 set — must
    return before ever constructing a boto3 client.
    """
    with (
        patch.object(cfg, "ecs_container_metadata_uri_v4", None),
        patch("boto3.client") as mock_boto_client,
    ):
        _emit_scale_kickstart_metric()

    mock_boto_client.assert_not_called()


def test_emit_scale_kickstart_metric_publishes_in_ecs():
    """In a real ECS task, publishes one Count datapoint to the
    job-submitted-{app_env} metric in the pyvar namespace."""
    mock_client = MagicMock()
    with (
        patch.object(cfg, "ecs_container_metadata_uri_v4", "http://169.254.170.2/v4/abc"),
        patch("api.routes.var._cw_client", None),
        patch("boto3.client", return_value=mock_client) as mock_boto_client,
    ):
        _emit_scale_kickstart_metric()

    mock_boto_client.assert_called_once_with("cloudwatch")
    mock_client.put_metric_data.assert_called_once()
    call_kwargs = mock_client.put_metric_data.call_args.kwargs
    assert call_kwargs["Namespace"] == "pyvar"
    assert call_kwargs["MetricData"][0]["MetricName"] == f"job-submitted-{cfg.app_env}"
    assert call_kwargs["MetricData"][0]["Value"] == 1.0


def test_emit_scale_kickstart_metric_survives_cloudwatch_failure():
    """The actual /var/compute response must never fail or slow down because
    this best-effort metric emission failed -- a CloudWatch outage, IAM
    change, or throttling must degrade silently, not propagate.
    """
    mock_client = MagicMock()
    mock_client.put_metric_data.side_effect = Exception("Throttling")
    with (
        patch.object(cfg, "ecs_container_metadata_uri_v4", "http://169.254.170.2/v4/abc"),
        patch("api.routes.var._cw_client", None),
        patch("boto3.client", return_value=mock_client),
    ):
        _emit_scale_kickstart_metric()  # must not raise
