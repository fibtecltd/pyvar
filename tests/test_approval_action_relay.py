"""tests/test_approval_action_relay.py — tests for
pyvar-cdk/lambda/approval_action_relay/handler.py.

Reasoning:
- Same pattern as tests/test_ses_suppression_handler.py: pyvar-cdk/lambda/
  has no pytest harness of its own — loaded here by file path with the
  required env var stubbed. No AWS calls happen at import time
  (boto3.client("sns") construction is lazy), so the module loads cleanly
  without credentials; handler()'s own sns.publish call is mocked by
  replacing the module-level `sns` attribute after import.
- parse_manual_approval_event/build_custom_notification are pure functions,
  tested directly without going through handler()/SNS-record wrapping.
- _REAL_APPROVAL_EVENT matches actual CodeStar Notifications payloads
  captured while diagnosing the missing prod-approval Slack notification
  (2026-08-22 to 2026-08-24 incident): no top-level "content" key exists,
  "additionalAttributes" is a sibling of "detail", and the approval token
  is detail["action-execution-id"]. The previous fixture here encoded
  AWS's documented-but-never-observed content.additionalAttributes.token
  schema instead — that mismatch is exactly what let the original handler
  bug (see its module docstring) pass this suite while silently skipping
  every real approval notification.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock

HANDLER_PATH = (
    Path(__file__).parent.parent / "pyvar-cdk" / "lambda" / "approval_action_relay" / "handler.py"
)


def _load_handler_module(monkeypatch):
    monkeypatch.setenv(
        "TARGET_TOPIC_ARN", "arn:aws:sns:eu-west-1:123456789012:pyvar-pipeline-notifications"
    )
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")

    spec = importlib.util.spec_from_file_location("approval_action_relay", HANDLER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The REAL CodeStar Notifications payload shape for
# codepipeline-pipeline-manual-approval-needed, confirmed against actual
# captured payloads for this account -- not AWS's documented content
# schema (see module docstring and handler.py's).
_REAL_APPROVAL_EVENT = {
    "account": "123456789012",
    "detailType": "CodePipeline Action Execution State Change",
    "region": "eu-west-1",
    "source": "aws.codepipeline",
    "notificationRuleArn": (
        "arn:aws:codestar-notifications:eu-west-1:123456789012:notificationrule/example"
    ),
    "detail": {
        "pipeline": "pyvar-dev-pipeline",
        "execution-id": "11111111-1111-4111-8111-111111111111",
        "start-time": "2026-08-24T06:05:07.104Z",
        "stage": "Prod",
        "action-execution-id": "abc-token-123",
        "action": "ApproveProductionDeploy",
        "state": "STARTED",
        "region": "eu-west-1",
        "type": {"owner": "AWS", "provider": "Manual", "category": "Approval", "version": "1"},
        "version": 7.0,
        "pipeline-execution-attempt": 1.0,
    },
    "resources": ["arn:aws:codepipeline:eu-west-1:123456789012:pyvar-dev-pipeline"],
    "additionalAttributes": {
        "externalEntityLink": "https://console.aws.amazon.com/codesuite/codepipeline/...",
        "customData": "Review dev deployment smoke tests before approving.",
    },
}


# ── parse_manual_approval_event ──────────────────────────────────────────────


def test_parse_extracts_all_fields_from_real_shape(monkeypatch):
    module = _load_handler_module(monkeypatch)
    fields = module.parse_manual_approval_event(_REAL_APPROVAL_EVENT)

    assert fields == {
        "pipeline": "pyvar-dev-pipeline",
        "stage": "Prod",
        "action": "ApproveProductionDeploy",
        "token": "abc-token-123",
        "region": "eu-west-1",
        "review_link": "https://console.aws.amazon.com/codesuite/codepipeline/...",
    }


def test_parse_falls_back_to_documented_content_schema_token(monkeypatch):
    """AWS's documented content.additionalAttributes.token schema — never
    observed for this account, but kept as a defensive fallback. See
    module docstring."""
    module = _load_handler_module(monkeypatch)
    event = {
        "detailType": "CodePipeline Action Execution State Change",
        "detail": {
            "pipeline": "pyvar-dev-pipeline",
            "stage": "Prod",
            "action": "ApproveProductionDeploy",
        },
        "content": {
            "additionalAttributes": {
                "token": "documented-schema-token",
                "approvalReviewLink": "https://example.com/review",
            }
        },
    }

    fields = module.parse_manual_approval_event(event)
    assert fields["token"] == "documented-schema-token"
    assert fields["review_link"] == "https://example.com/review"


def test_parse_falls_back_to_detail_approval_token(monkeypatch):
    """Older direct-SNS-on-approval-action shape — see module docstring."""
    module = _load_handler_module(monkeypatch)
    event = {
        "detailType": "CodePipeline Action Execution State Change",
        "detail": {
            "pipeline": "pyvar-dev-pipeline",
            "stage": "Prod",
            "action": "ApproveProductionDeploy",
            "approval": {"token": "fallback-token"},
        },
    }

    fields = module.parse_manual_approval_event(event)
    assert fields["token"] == "fallback-token"


def test_parse_prefers_real_shape_token_over_fallback_paths(monkeypatch):
    """detail.action-execution-id must win when multiple field paths are
    somehow present at once."""
    module = _load_handler_module(monkeypatch)
    event = {
        "detailType": "CodePipeline Action Execution State Change",
        "detail": {
            "pipeline": "pyvar-dev-pipeline",
            "stage": "Prod",
            "action": "ApproveProductionDeploy",
            "action-execution-id": "real-shape-token",
            "approval": {"token": "fallback-token"},
        },
        "content": {"additionalAttributes": {"token": "documented-schema-token"}},
    }

    fields = module.parse_manual_approval_event(event)
    assert fields["token"] == "real-shape-token"


def test_parse_returns_none_when_token_missing(monkeypatch):
    module = _load_handler_module(monkeypatch)
    event = {
        "detailType": "CodePipeline Action Execution State Change",
        "detail": {"pipeline": "p", "stage": "s", "action": "a"},
    }
    assert module.parse_manual_approval_event(event) is None


def test_parse_returns_none_for_unrelated_event_shape(monkeypatch):
    """A pipeline-execution-succeeded event has no action/token at all --
    must not be misparsed as an approval-needed event."""
    module = _load_handler_module(monkeypatch)
    event = {
        "detailType": "CodePipeline Pipeline Execution State Change",
        "detail": {"pipeline": "pyvar-dev-pipeline", "state": "SUCCEEDED"},
    }
    assert module.parse_manual_approval_event(event) is None


def test_parse_returns_none_when_review_link_and_region_absent_but_still_no_token(monkeypatch):
    module = _load_handler_module(monkeypatch)
    event = {"detail": {}}
    assert module.parse_manual_approval_event(event) is None


# ── build_custom_notification ────────────────────────────────────────────────


def test_build_custom_notification_shape(monkeypatch):
    module = _load_handler_module(monkeypatch)
    fields = {
        "pipeline": "pyvar-dev-pipeline",
        "stage": "Prod",
        "action": "ApproveProductionDeploy",
        "token": "abc-token-123",
        "region": "eu-west-1",
        "review_link": "https://example.com/review",
    }

    notification = module.build_custom_notification(fields)

    assert notification["version"] == "1.0"
    assert notification["source"] == "custom"
    assert "pyvar-dev-pipeline" in notification["content"]["title"]
    assert "https://example.com/review" in notification["content"]["description"]
    assert notification["metadata"]["additionalContext"] == {
        "pipelineName": "pyvar-dev-pipeline",
        "stageName": "Prod",
        "actionName": "ApproveProductionDeploy",
        "approvalToken": "abc-token-123",
        "region": "eu-west-1",
    }


def test_build_custom_notification_omits_review_link_when_absent(monkeypatch):
    module = _load_handler_module(monkeypatch)
    fields = {
        "pipeline": "p",
        "stage": "s",
        "action": "a",
        "token": "t",
        "region": "",
        "review_link": "",
    }
    notification = module.build_custom_notification(fields)
    assert "Review in CodePipeline" not in notification["content"]["description"]


# ── handler ───────────────────────────────────────────────────────────────────


def _sns_record(message: dict) -> dict:
    return {"Sns": {"Message": json.dumps(message)}}


def test_handler_publishes_custom_notification_for_valid_event(monkeypatch):
    module = _load_handler_module(monkeypatch)
    mock_sns = MagicMock()
    monkeypatch.setattr(module, "sns", mock_sns)

    result = module.handler({"Records": [_sns_record(_REAL_APPROVAL_EVENT)]}, None)

    assert result == {"relayed_count": 1}
    mock_sns.publish.assert_called_once()
    kwargs = mock_sns.publish.call_args.kwargs
    assert kwargs["TopicArn"] == "arn:aws:sns:eu-west-1:123456789012:pyvar-pipeline-notifications"
    published = json.loads(kwargs["Message"])
    assert published["source"] == "custom"
    assert published["metadata"]["additionalContext"]["approvalToken"] == "abc-token-123"


def test_handler_skips_unrecognised_event_without_publishing(monkeypatch):
    module = _load_handler_module(monkeypatch)
    mock_sns = MagicMock()
    monkeypatch.setattr(module, "sns", mock_sns)

    event = {"detail": {"pipeline": "p", "state": "SUCCEEDED"}}
    result = module.handler({"Records": [_sns_record(event)]}, None)

    assert result == {"relayed_count": 0}
    mock_sns.publish.assert_not_called()


def test_handler_one_malformed_record_does_not_abort_batch(monkeypatch):
    module = _load_handler_module(monkeypatch)
    mock_sns = MagicMock()
    monkeypatch.setattr(module, "sns", mock_sns)

    malformed = {"Sns": {"Message": "not-json"}}
    valid = _sns_record(_REAL_APPROVAL_EVENT)
    result = module.handler({"Records": [malformed, valid]}, None)

    assert result == {"relayed_count": 1}
    mock_sns.publish.assert_called_once()
