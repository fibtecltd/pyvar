"""
stacks/alb_waf_stack.py — Regional WAF WebACL attached to the ALB (eu-west-1)

Option 1 fallback for when pyvar-dev-edge (CloudFront + WAF us-east-1) is
blocked by AWS account verification.

Reasoning:
- WAF WebACLs for CloudFront MUST be in us-east-1 (CLOUDFRONT scope).
  WAF WebACLs for ALB/API Gateway must be in the same region as the
  resource (REGIONAL scope). This stack deploys a REGIONAL WebACL in
  eu-west-1 and associates it directly with the ALB.
- Rule set is intentionally identical to edge_stack.py: CommonRuleSet,
  KnownBadInputs, and per-IP rate limiting. This ensures the same
  protection baseline regardless of which path is active.
- The existing ALB origin-verify listener rules (SEC-1) are NOT modified
  by this stack — they remain active and continue to gate direct access.
- When pyvar-dev-edge eventually deploys (CloudFront + WAF us-east-1),
  this stack can be left in place (defence in depth: regional WAF on ALB
  + edge WAF on CloudFront) or torn down — operator choice.
- Rate limiting at the regional WAF level applies to direct ALB hits.
  Once CloudFront is active, the edge WAF applies its own rate limit at
  the PoP before requests reach the ALB.

Deploy (Option 1 active):
    cdk deploy pyvar-dev-alb-waf --context env=dev --context account=ACCOUNT

Tear down (once edge is verified and deployed, if desired):
    cdk destroy pyvar-dev-alb-waf --context env=dev --context account=ACCOUNT
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import Stack
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_wafv2 as waf
from constructs import Construct

from config import PyvarConfig


class AlbWafStack(Stack):

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        cfg: PyvarConfig,
        alb: elbv2.ApplicationLoadBalancer,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)

        # ── Regional WAF WebACL (eu-west-1) ───────────────────────────────────
        # scope=REGIONAL is required for ALB association.
        # Rule set mirrors edge_stack.py WebACL exactly (same names, priorities,
        # managed rule groups) — only scope differs.
        web_acl = waf.CfnWebACL(
            self,
            "AlbWebAcl",
            name=f"pyvar-{cfg.env_name}-alb-waf",
            scope="REGIONAL",
            default_action=waf.CfnWebACL.DefaultActionProperty(allow={}),
            visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name=f"pyvar-{cfg.env_name}-alb-waf",
                sampled_requests_enabled=True,
            ),
            rules=[
                # AWS Managed: Core rule set (OWASP Top 10 mitigations)
                waf.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesCommonRuleSet",
                    priority=10,
                    override_action=waf.CfnWebACL.OverrideActionProperty(none={}),
                    statement=waf.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=waf.CfnWebACL.ManagedRuleGroupStatementProperty(
                            name="AWSManagedRulesCommonRuleSet",
                            vendor_name="AWS",
                        )
                    ),
                    visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="CommonRuleSet",
                        sampled_requests_enabled=True,
                    ),
                ),
                # AWS Managed: Known bad inputs (Log4Shell, SSRF, etc.)
                waf.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesKnownBadInputsRuleSet",
                    priority=20,
                    override_action=waf.CfnWebACL.OverrideActionProperty(none={}),
                    statement=waf.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=waf.CfnWebACL.ManagedRuleGroupStatementProperty(
                            name="AWSManagedRulesKnownBadInputsRuleSet",
                            vendor_name="AWS",
                        )
                    ),
                    visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="KnownBadInputs",
                        sampled_requests_enabled=True,
                    ),
                ),
                # Rate limiting: 100 requests per 5 minutes per IP
                # Prevents credential stuffing and API key brute-forcing
                waf.CfnWebACL.RuleProperty(
                    name="RateLimitPerIp",
                    priority=30,
                    action=waf.CfnWebACL.RuleActionProperty(block={}),
                    statement=waf.CfnWebACL.StatementProperty(
                        rate_based_statement=waf.CfnWebACL.RateBasedStatementProperty(
                            aggregate_key_type="IP",
                            limit=100,
                        )
                    ),
                    visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="RateLimit",
                        sampled_requests_enabled=True,
                    ),
                ),
            ],
        )

        # ── Associate WebACL with ALB ──────────────────────────────────────────
        # CfnWebACLAssociation requires the full ALB ARN and the WebACL ARN.
        # alb.load_balancer_arn is exposed by ApiStack via self.alb.
        waf.CfnWebACLAssociation(
            self,
            "AlbWebAclAssociation",
            resource_arn=alb.load_balancer_arn,
            web_acl_arn=web_acl.attr_arn,
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "AlbWafAcl", value=web_acl.attr_arn)
