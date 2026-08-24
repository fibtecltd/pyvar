"""
lambda/approval_action_relay/handler.py — relay ApproveProductionDeploy
notifications into a Chatbot custom notification carrying an approve button.

Reasoning:
- Native (CodeStar Notifications) manual-approval-needed messages have
  reliably reached AWS Chatbot's Slack delivery pipeline as PLAIN text
  (confirmed via repro testing: 3/3 real and synthetic native-shaped events
  delivered, once the earlier channel-membership issue was fixed) but never
  render an Approve/Reject action in Slack. Chatbot's Custom Actions feature
  (docs.aws.amazon.com/chatbot/latest/adminguide/custom-actions.html) can
  attach a button that runs a CLI command using the channel's own IAM role
  -- but only on `custom`-schema notifications with the token/pipeline/
  stage/action exposed via metadata.additionalContext, not (so far as
  confirmed from docs alone) on native CodePipeline-shaped ones. This
  Lambda is the bridge: parse the native event, republish an equivalent
  `custom`-schema one Chatbot will let us attach a button to.
- Deliberately NOT republished onto the same topic it's read from -- this
  Lambda is subscribed to a NEW, narrowly-scoped SNS topic
  (pyvar-pipeline-approval-raw) that ONLY carries
  codepipeline-pipeline-manual-approval-needed events (a second, narrower
  CodeStarNotifications.NotificationRule in pipeline_stack.py), while the
  existing pyvar-pipeline-notifications topic keeps carrying every OTHER
  event type (failed/succeeded) straight to Chatbot as before, unchanged.
  The reformatted custom message is published back onto that EXISTING
  topic -- inheriting a delivery path already proven reliable for
  `custom`-shaped messages (2/2 in repro testing), rather than adding a new
  untested one. If this Lambda instead republished onto the SAME topic it
  reads from, Chatbot would receive the native message AND the custom one
  for the same approval -- two Slack messages per approval, not one.
- FIELD-VALIDATED against real captured payloads (2026-08-24): there is no
  top-level "content" key in any real CodeStar Notifications payload seen
  for this account -- "additionalAttributes" is a sibling of "detail", not
  nested under a "content" object. The approval token is at
  detail["action-execution-id"] (this equals the actionExecutionId/token
  returned by `codepipeline get-pipeline-state`), and the review link is at
  the top-level additionalAttributes.externalEntityLink. A synthetic
  manual-approval-needed test published directly onto
  pyvar-pipeline-approval-raw confirmed the original field paths below
  (content.additionalAttributes.token, detail.approval.token) never match
  for this account and would have silently skipped every real approval
  notification, not just the test. Those paths are kept as secondary
  fallbacks only, matching AWS's documented-but-unobserved content schema,
  in case some other event source ever does send that shape.
"""

from __future__ import annotations

import json
import os
from typing import Any

import boto3

TARGET_TOPIC_ARN = os.environ["TARGET_TOPIC_ARN"]

sns = boto3.client("sns")

_MANUAL_APPROVAL_EVENT_TYPE = "codepipeline-pipeline-manual-approval-needed"


def parse_manual_approval_event(raw_message: dict[str, Any]) -> dict[str, str] | None:
    """Pure extraction — no boto3 calls, spot-checkable without credentials.

    Args:
        raw_message: The decoded body of one SNS record's Message field —
            a CodeStar Notifications payload for CodePipeline.

    Returns:
        dict[str, str] | None: pipeline/stage/action/token/region/
            review_link, or None if this isn't a recognisable manual-
            approval-needed event, or a required field is missing.
    """
    detail = raw_message.get("detail", {})
    content = raw_message.get("content", {})
    content_attrs = content.get("additionalAttributes", {})
    top_attrs = raw_message.get("additionalAttributes", {})

    event_type = raw_message.get("detailType") or raw_message.get("detail-type")
    # Token field path, in priority order:
    #   1. detail["action-execution-id"] — the real path for this account,
    #      confirmed against actual captured payloads (see module
    #      docstring). This IS the approval token CodePipeline expects
    #      back via PutApprovalResult.
    #   2. content.additionalAttributes.token / detail.approval.token —
    #      AWS's documented but (for this account) never-observed content
    #      schema. Kept as a defensive fallback only.
    token = (
        detail.get("action-execution-id")
        or content_attrs.get("token")
        or detail.get("approval", {}).get("token")
    )
    is_approval_shaped = bool(detail.get("action")) and bool(token)
    if event_type is None and not is_approval_shaped:
        return None

    pipeline = detail.get("pipeline")
    stage = detail.get("stage")
    action = detail.get("action")
    region = raw_message.get("region") or detail.get("region")
    # Review link, in priority order: real payloads carry this at the
    # top-level additionalAttributes.externalEntityLink (often an empty
    # string for this pipeline's ApproveProductionDeploy action).
    # Documented content-schema paths kept as a defensive fallback only.
    review_link = (
        top_attrs.get("externalEntityLink")
        or content_attrs.get("approvalReviewLink")
        or detail.get("approval", {}).get("approvalReviewLink")
    )

    if not (pipeline and stage and action and token):
        return None

    return {
        "pipeline": pipeline,
        "stage": stage,
        "action": action,
        "token": token,
        "region": region or "",
        "review_link": review_link or "",
    }


def build_custom_notification(fields: dict[str, str]) -> dict[str, Any]:
    """Chatbot custom-notification schema, with the approval fields exposed
    under metadata.additionalContext for a Custom Action's CLI command
    template to reference (e.g. `--token $additionalContext.approvalToken`
    -- exact variable-reference syntax to be confirmed live per this
    module's own docstring)."""
    pipeline, stage, action = fields["pipeline"], fields["stage"], fields["action"]
    return {
        "version": "1.0",
        "source": "custom",
        "content": {
            "textType": "client-markdown",
            "title": f":rotating_light: Manual approval needed — {pipeline}",
            "description": (
                f"Pipeline **{pipeline}** stage **{stage}** is waiting on "
                f"action **{action}**."
                + (
                    f"\n\n<{fields['review_link']}|Review in CodePipeline>"
                    if fields["review_link"]
                    else ""
                )
            ),
        },
        "metadata": {
            "summary": f"{pipeline}/{stage}/{action} awaiting approval",
            "additionalContext": {
                "pipelineName": pipeline,
                "stageName": stage,
                "actionName": action,
                "approvalToken": fields["token"],
                "region": fields["region"],
            },
        },
    }


def _log_raw_event(message_str: str) -> None:
    # See module docstring — unconditional, not just on parse failure, so
    # the very first real trigger is diagnosable even if parsing succeeds
    # but on the wrong field paths.
    print(f"approval_relay_raw_event: {message_str}")


def handler(event, context):  # noqa: ANN001, ANN201 — Lambda entrypoint signature is fixed
    relayed_count = 0

    for record in event.get("Records", []):
        try:
            message_str = record["Sns"]["Message"]
            _log_raw_event(message_str)
            raw_message = json.loads(message_str)

            fields = parse_manual_approval_event(raw_message)
            if fields is None:
                print(f"approval_relay_skipped_unrecognised_event: {message_str[:200]}")
                continue

            custom_notification = build_custom_notification(fields)
            sns.publish(
                TopicArn=TARGET_TOPIC_ARN,
                Message=json.dumps(custom_notification),
            )
            relayed_count += 1
        except (KeyError, json.JSONDecodeError) as exc:
            # One malformed record must not abort the whole batch -- an
            # unhandled exception here would make SNS retry the entire
            # invocation, replaying already-processed records. Same
            # philosophy as lambda/ses_suppression_handler/handler.py.
            print(f"approval_relay_record_failed: {exc}")

    return {"relayed_count": relayed_count}
