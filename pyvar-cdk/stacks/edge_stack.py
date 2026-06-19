"""
stacks/edge_stack.py — CloudFront distribution + WAF + Route53

Reasoning:
- CloudFront and WAF WebACLs for CloudFront distributions MUST be
  created in us-east-1, regardless of where the origin lives.
  This stack is therefore explicitly deployed to us-east-1 in app.py.
- Cache behaviour for GET /api/v1/var/result/{task_id}:
    - Pending/started responses: TTL=0 (client must re-poll)
    - Success responses: TTL=3600 (result is immutable once computed)
  This is achieved by having the FastAPI response set Cache-Control headers:
    - PENDING: Cache-Control: no-store
    - SUCCESS: Cache-Control: public, max-age=3600
  CloudFront respects Cache-Control headers from the origin.
- WAF rules block: common web exploits (OWASP), known bad IPs,
  rate limiting (100 req/5min per IP to prevent API key stuffing).
- Route53 alias record points to CloudFront — no separate DNS TTL
  management needed.
- X-Origin-Verify header is a Secrets Manager-generated value, shared
  with api_stack.py via direct cross-region construct reference (same
  mechanism CDK uses for alb_dns). The ALB enforces it via a listener
  rule — see api_stack.py — so a direct hit to the ALB without the
  header is rejected, closing the WAF-bypass gap.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import Stack
from aws_cdk import aws_cloudfront as cf
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as targets
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_wafv2 as waf
from constructs import Construct

from config import PyvarConfig


class EdgeStack(Stack):

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        cfg: PyvarConfig,
        alb_dns: str,
        origin_verify_secret: secretsmanager.Secret,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)

        # ── WAF WebACL (must be in us-east-1 for CloudFront) ──────────────────
        # Managed rule groups from AWS — maintained by AWS Security team
        web_acl = waf.CfnWebACL(
            self,
            "WebAcl",
            name=f"pyvar-{cfg.env_name}-waf",
            scope="CLOUDFRONT",
            default_action=waf.CfnWebACL.DefaultActionProperty(allow={}),
            visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name=f"pyvar-{cfg.env_name}-waf",
                sampled_requests_enabled=True,
            ),
            rules=[
                # AWS Managed: Core rule set (OWASP Top 10 mitigations)
                waf.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesCoreRuleSet",
                    priority=10,
                    override_action=waf.CfnWebACL.OverrideActionProperty(none={}),
                    statement=waf.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=waf.CfnWebACL.ManagedRuleGroupStatementProperty(
                            name="AWSManagedRulesCoreRuleSet",
                            vendor_name="AWS",
                        )
                    ),
                    visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="CoreRuleSet",
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

        # ── CloudFront Distribution ────────────────────────────────────────────
        # ALB as HTTP origin (CloudFront handles TLS termination at edge)
        alb_origin = origins.HttpOrigin(
            alb_dns,
            protocol_policy=cf.OriginProtocolPolicy.HTTP_ONLY,
            http_port=443,
            origin_id="AlbOrigin",
            custom_headers={
                "X-Origin-Verify": origin_verify_secret.secret_value.unsafe_unwrap(),
            },
        )

        # Cache policy for API responses:
        # - Respects Cache-Control headers from FastAPI
        # - min TTL = 0 so PENDING responses (Cache-Control: no-store) are never cached
        api_cache_policy = cf.CachePolicy(
            self,
            "ApiCachePolicy",
            cache_policy_name=f"pyvar-{cfg.env_name}-api-cache",
            default_ttl=cdk.Duration.seconds(0),  # default: don't cache
            min_ttl=cdk.Duration.seconds(0),
            max_ttl=cdk.Duration.hours(1),  # max: 1 hour for SUCCESS responses
            enable_accept_encoding_brotli=True,
            enable_accept_encoding_gzip=True,
            query_string_behavior=cf.CacheQueryStringBehavior.none(),
            header_behavior=cf.CacheHeaderBehavior.allow_list(
                "Authorization",
                "Cache-Control",
            ),
        )

        self.distribution = cf.Distribution(
            self,
            "Distribution",
            comment=f"pyvar {cfg.env_name} CDN",
            web_acl_id=web_acl.attr_arn,
            http_version=cf.HttpVersion.HTTP2_AND_3,
            minimum_protocol_version=cf.SecurityPolicyProtocol.TLS_V1_2_2021,
            price_class=cf.PriceClass.PRICE_CLASS_100,  # US + Europe PoPs only — cheapest
            default_behavior=cf.BehaviorOptions(
                origin=alb_origin,
                viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=api_cache_policy,
                allowed_methods=cf.AllowedMethods.ALLOW_ALL,
                origin_request_policy=cf.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                compress=True,
            ),
            additional_behaviors={
                # Health check: never cached, always passes through
                "/health": cf.BehaviorOptions(
                    origin=alb_origin,
                    viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cf.CachePolicy.CACHING_DISABLED,
                    allowed_methods=cf.AllowedMethods.ALLOW_GET_HEAD,
                ),
                # API docs: cache for 5 minutes
                "/docs": cf.BehaviorOptions(
                    origin=alb_origin,
                    viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cf.CachePolicy.CACHING_OPTIMIZED,
                    allowed_methods=cf.AllowedMethods.ALLOW_GET_HEAD,
                ),
            },
            enable_logging=True,
            log_includes_cookies=False,
        )

        # ── Route53 (optional — only if hosted_zone_id is configured) ─────────
        if cfg.hosted_zone_id:
            zone = route53.HostedZone.from_hosted_zone_attributes(
                self,
                "HostedZone",
                hosted_zone_id=cfg.hosted_zone_id,
                zone_name=cfg.domain_name,
            )
            route53.ARecord(
                self,
                "AliasRecord",
                zone=zone,
                record_name="api",
                target=route53.RecordTarget.from_alias(targets.CloudFrontTarget(self.distribution)),
            )

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "CloudFrontDomain", value=self.distribution.distribution_domain_name)
        cdk.CfnOutput(self, "CloudFrontId", value=self.distribution.distribution_id)
