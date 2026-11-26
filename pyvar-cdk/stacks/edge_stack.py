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

Cost-explosion protection (P11 items 1 + 3, docs/p11-pre-launch-hardening.md
§1) — two more rules on the same WebACL, same reasoning as the existing
per-IP RateLimitPerIp rule above, extended to cover what it structurally
can't:
- AggregateRateLimit (priority 25): a single rate-based rule with
  aggregate_key_type="CONSTANT" — one shared bucket across every request
  regardless of source IP, unlike RateLimitPerIp's per-IP buckets. Bounds
  worst-case aggregate cost from many simultaneous low-rate clients (a
  traffic spike, or the pyvar MCP server's AI-agent usage pattern flagged
  as an open question in docs/p10-skills-and-plugin-plan.md) that no
  per-IP rule can see. AGGREGATE_RATE_LIMIT_PER_5MIN is a conservative
  placeholder pending a real traffic baseline post-launch (P11 §7) — revisit
  once there's real public traffic to size it against, don't treat 6000 as
  load-bearing today.
- EmergencyKillSwitch (priority 0, evaluated first): a "block everything"
  rule matching the user's "zero whitelisting" request, adapted to this
  architecture's actual control point (this WebACL) rather than the API
  Gateway resource policy the original request assumed — this deployment
  has no API Gateway; traffic flows CloudFront -> WAF -> ALB -> Fargate.
  Ships with action=count (INERT) so deploying/redeploying this rule never
  changes live traffic behaviour by itself — a normal `cdk deploy` is always
  safe. The actual emergency toggle is scripts/toggle_kill_switch.sh, which
  flips this rule's Action between Count and Block via a direct
  `aws wafv2 update-web-acl` call — NOT a CDK redeploy, which takes minutes
  and defeats the point of an emergency switch. Running `cdk deploy` again
  after a manual toggle resets this rule back to Count (CloudFormation
  drift) — intentional: the kill switch is a short-lived emergency measure,
  not a persistent state meant to survive the next normal deploy. See the
  script's own header comment for the full runbook.

_match_all_statement() (below) — both rules above need an unconditional
"matches every request" statement (the kill switch AS its own match
condition; AggregateRateLimit as its required ScopeDownStatement, see next
paragraph) built from SizeConstraintStatement(UriPath length >= 0), which
is always true and is AWS's own documented example shape for a
ScopeDownStatement, rather than a ByteMatchStatement with an empty
search_string on the theory that an empty prefix matches everything: that
approach is NOT documented as valid AWS behaviour (checked directly against
AWS's own CloudFormation User Guide, not assumed), and this stack has
already been burned once by trusting an undocumented-but-plausible-looking
WAFv2 construct shape (see the ScopeDownStatement paragraph below) — not
worth the same risk twice in the same file.

FIX (post-deploy, real production incident, not a synth-time catch): the
very first deploy of AggregateRateLimit failed with "A required field is
missing from the parameter., field: SCOPE_DOWN, parameter:
RateBasedStatement" — confirmed directly against AWS's own CloudFormation
User Guide: a RateBasedStatement with aggregate_key_type="CONSTANT" is
REQUIRED to carry a ScopeDownStatement (CloudFormation's own schema marks
the field optional; WAFv2's CreateWebACL/UpdateWebACL API enforces it
conditionally at deploy time regardless — exactly the class of gap
`cdk synth` cannot catch without live AWS credentials, flagged as a known
limitation when this rule was first added). The CloudFormation stack itself
rolled back cleanly (UPDATE_ROLLBACK_COMPLETE) and only the Dev stage was
affected — Prod was never reached — but every subsequent deploy would have
kept failing at the same step until fixed. scope_down_statement below is
set to the same _match_all_statement() the kill switch uses: this rule is
deliberately meant to be a true global bucket with no narrowing, and a
scope-down that matches unconditionally preserves that while satisfying
the now-confirmed-mandatory field.

No-sign-up trial lane (docs/plan-trial-lane-throttle.md, layers L5 and L8; trial lane PR 3). The lane is
POST /api/v1/trial/{challenge,ticket,run/<function>}. What this stack adds for it, all scoped to that path
(a starts-with match on the URL-decoded, normalised path) and none of it touching any other route:
- TrialKillSwitch (priority 5): "block the trial path", shipped in Count like EmergencyKillSwitch and
  flipped the same way (scripts/toggle_kill_switch.sh status|enable|disable <env> TrialKillSwitch). The
  lane's own switch is a Redis key (scripts/trial_ctl.py off); this is the edge's second lever, for when the
  API itself is the problem.
- TrialRateLimitPerIp (21): 30 requests per 600 s per source address; TrialRateLimitPerAsn (22): 600 per
  600 s per network (WAF's own ASN aggregation key, so it does not depend on the header below);
  TrialRateLimitAll (23): 300 per 300 s for the whole path (CONSTANT, hence the mandatory scope-down). All
  three sit BEFORE AggregateRateLimit (25), so a trial flood is stopped here and does not use up the 6,000
  that every other caller shares. The lowest limit WAF accepts is 10 and the longest window 600 s, so WAF
  alone cannot say "2 tickets a day"; that is the API's job (L6).
- A cache behaviour for the path with its own origin request policy that forwards `CloudFront-Viewer-ASN`
  to the API (L5, the per-network share). CloudFront adds that header only when an origin request policy
  names it; the default behaviour's policy (ALL_VIEWER_EXCEPT_HOST_HEADER) does not. The policy is an
  allow-list (the User-Agent, the plugin's X-Pyvar-Client label and that header): the lane reads nothing
  else, and Authorization reaches the origin because it is in the cache policy's key, as for every route.
- A us-east-1 SNS topic and one alarm (blocked requests of the three rate rules above 1,000 in 5 minutes).
  An alarm must live in the region of its metric and publish to a topic of its own region, so this cannot
  use the alerts stack's topic. Like that topic, it is created without subscribers: add one after deploy.
The lane's other alarms count its log lines in the API's own region (stacks/alerts_stack.py).

Typed-question assistant (api/assistant/routes.py, POST /api/v1/assistant/ask, off in every environment): one rule,
AssistantRateLimitPerIp (24): 30 requests per 300 s per source address, scoped to that path (the same URL-decoded,
normalised starts-with match as the trial rules) and placed BEFORE AggregateRateLimit (25), so a flood on the
assistant is stopped here and does not use up the 6,000 that every other caller shares. It is a backstop for abuse,
far above what a person types: the route's own quotas (anonymous 10 an hour per address; 40, 200 and 500 a day by
tier) are the real limits. The menu buttons are static files under /assistant/bank/, not under this path.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import Duration, Stack
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cf
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as targets
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_sns as sns
from aws_cdk import aws_wafv2 as waf
from constructs import Construct

from config import PyvarConfig

# Aggregate (all-clients-combined) request cap per 5-minute window — see the
# AggregateRateLimit rule below. Conservative placeholder, not yet sized
# against real public traffic (P11 §7 open item) -- revisit post-launch.
AGGREGATE_RATE_LIMIT_PER_5MIN = 6000

# The no-sign-up trial lane (api/routes/trial.py, mounted under the API's /api/v1). Every trial rule and the
# trial cache behaviour key on this one path; tests/test_cdk_trial_lane.py pins it to the route's own prefix.
TRIAL_PATH_PREFIX = "/api/v1/trial/"
TRIAL_PATH_PATTERN = TRIAL_PATH_PREFIX + "*"

# How long CloudFront's standard access logs are kept. They hold each request's IP address and URL (query
# string included), so the privacy policy states this number (portal/privacy.html section 4) and
# tests/test_cdk_access_log_retention.py pins the two together: change both or neither. 90 days covers a
# quarterly look-back (the Googlebot check in docs/seo-crawl-investigation.md read 46 days) without keeping
# addresses indefinitely, which is what happened before the rule existed.
ACCESS_LOG_RETENTION_DAYS = 90
# docs/plan-trial-lane-throttle.md L8: per source address, per network, and for the path as a whole.
TRIAL_LIMIT_PER_IP = 30  # per TRIAL_WINDOW_PER_IP_ASN_SEC
TRIAL_LIMIT_PER_ASN = 600  # per TRIAL_WINDOW_PER_IP_ASN_SEC
TRIAL_WINDOW_PER_IP_ASN_SEC = 600
TRIAL_LIMIT_ALL = 300  # per TRIAL_WINDOW_ALL_SEC
TRIAL_WINDOW_ALL_SEC = 300
# The three blocking rules' metric names (WAF's `Rule` metric dimension), in one place for the alarm below.
TRIAL_RATE_RULE_METRICS = ("TrialRateLimitPerIp", "TrialRateLimitPerAsn", "TrialRateLimitAll")
# Blocks of those rules in 5 minutes that page someone: a flood is under way, or a real caller is being refused.
TRIAL_WAF_BLOCKS_ALARM_THRESHOLD = 1000

# The typed-question route (api/assistant/routes.py, mounted under the API's /api/v1; off in every environment).
# tests/test_cdk_assistant_infra.py pins the prefix to the route's own.
ASSISTANT_PATH_PREFIX = "/api/v1/assistant/"
# Per source address, per ASSISTANT_WINDOW_PER_IP_SEC: a backstop; the route's own quotas are the real limits.
ASSISTANT_LIMIT_PER_IP = 30
ASSISTANT_WINDOW_PER_IP_SEC = 300


def _match_all_statement() -> waf.CfnWebACL.StatementProperty:
    """An unconditional "matches every request" WAFv2 statement.

    SizeConstraintStatement(UriPath length >= 0) is always true (every URI
    path has non-negative length) and is the shape AWS's own documented
    CONSTANT-aggregation example uses for a ScopeDownStatement -- see the
    module docstring's ScopeDownStatement paragraph for why this is used
    instead of an empty-search-string ByteMatchStatement.
    """
    return waf.CfnWebACL.StatementProperty(
        size_constraint_statement=waf.CfnWebACL.SizeConstraintStatementProperty(
            field_to_match=waf.CfnWebACL.FieldToMatchProperty(uri_path={}),
            comparison_operator="GE",
            size=0,
            text_transformations=[
                waf.CfnWebACL.TextTransformationProperty(priority=0, type="NONE")
            ],
        )
    )


def _trial_path_statement() -> waf.CfnWebACL.StatementProperty:
    """Matches a request whose path starts with TRIAL_PATH_PREFIX, after URL decoding and path normalisation.

    The transformations matter: the API decodes %-escapes and collapses `//` before routing, so a match on the
    raw path would let `/api/v1/%74rial/...` or `/api/v1//trial/...` reach the lane around these rules.
    """
    return waf.CfnWebACL.StatementProperty(
        byte_match_statement=waf.CfnWebACL.ByteMatchStatementProperty(
            field_to_match=waf.CfnWebACL.FieldToMatchProperty(uri_path={}),
            positional_constraint="STARTS_WITH",
            search_string=TRIAL_PATH_PREFIX,
            text_transformations=[
                waf.CfnWebACL.TextTransformationProperty(priority=0, type="URL_DECODE"),
                waf.CfnWebACL.TextTransformationProperty(priority=1, type="NORMALIZE_PATH"),
            ],
        )
    )


def _trial_rate_rule(
    name: str,
    priority: int,
    *,
    aggregate_key_type: str,
    limit: int,
    window_sec: int,
    custom_keys: list[waf.CfnWebACL.RateBasedStatementCustomKeyProperty] | None = None,
) -> waf.CfnWebACL.RuleProperty:
    """One blocking rate rule on the trial path; `name` is also its CloudWatch metric name."""
    return waf.CfnWebACL.RuleProperty(
        name=name,
        priority=priority,
        action=waf.CfnWebACL.RuleActionProperty(block={}),
        statement=waf.CfnWebACL.StatementProperty(
            rate_based_statement=waf.CfnWebACL.RateBasedStatementProperty(
                aggregate_key_type=aggregate_key_type,
                limit=limit,
                evaluation_window_sec=window_sec,
                custom_keys=custom_keys,
                scope_down_statement=_trial_path_statement(),
            )
        ),
        visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
            cloud_watch_metrics_enabled=True,
            metric_name=name,
            sampled_requests_enabled=True,
        ),
    )


def _assistant_path_statement() -> waf.CfnWebACL.StatementProperty:
    """Matches a request whose path starts with ASSISTANT_PATH_PREFIX, after URL decoding and path normalisation.

    The same shape as `_trial_path_statement`, for the same reason: the API decodes %-escapes and collapses `//`
    before routing, so a match on the raw path could be walked around.
    """
    return waf.CfnWebACL.StatementProperty(
        byte_match_statement=waf.CfnWebACL.ByteMatchStatementProperty(
            field_to_match=waf.CfnWebACL.FieldToMatchProperty(uri_path={}),
            positional_constraint="STARTS_WITH",
            search_string=ASSISTANT_PATH_PREFIX,
            text_transformations=[
                waf.CfnWebACL.TextTransformationProperty(priority=0, type="URL_DECODE"),
                waf.CfnWebACL.TextTransformationProperty(priority=1, type="NORMALIZE_PATH"),
            ],
        )
    )


def _assistant_rate_rule() -> waf.CfnWebACL.RuleProperty:
    """The blocking per-address rate rule on the typed-question path; its name is also its metric name."""
    name = "AssistantRateLimitPerIp"
    return waf.CfnWebACL.RuleProperty(
        name=name,
        priority=24,
        action=waf.CfnWebACL.RuleActionProperty(block={}),
        statement=waf.CfnWebACL.StatementProperty(
            rate_based_statement=waf.CfnWebACL.RateBasedStatementProperty(
                aggregate_key_type="IP",
                limit=ASSISTANT_LIMIT_PER_IP,
                evaluation_window_sec=ASSISTANT_WINDOW_PER_IP_SEC,
                scope_down_statement=_assistant_path_statement(),
            )
        ),
        visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
            cloud_watch_metrics_enabled=True,
            metric_name=name,
            sampled_requests_enabled=True,
        ),
    )


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
                # Emergency kill switch — priority 0, evaluated before every other
                # rule. Ships inert (action=count); see the module docstring and
                # scripts/toggle_kill_switch.sh for how this is actually engaged.
                waf.CfnWebACL.RuleProperty(
                    name="EmergencyKillSwitch",
                    priority=0,
                    action=waf.CfnWebACL.RuleActionProperty(count={}),
                    statement=_match_all_statement(),
                    visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="EmergencyKillSwitch",
                        sampled_requests_enabled=True,
                    ),
                ),
                # Trial lane kill switch -- priority 5, scoped to the trial path only, inert (count) like
                # the one above and flipped the same way (scripts/toggle_kill_switch.sh ... TrialKillSwitch).
                waf.CfnWebACL.RuleProperty(
                    name="TrialKillSwitch",
                    priority=5,
                    action=waf.CfnWebACL.RuleActionProperty(count={}),
                    statement=_trial_path_statement(),
                    visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="TrialKillSwitch",
                        sampled_requests_enabled=True,
                    ),
                ),
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
                # Trial lane rate limits (module docstring): before the aggregate rule, so a flood on the
                # trial path is refused here and does not count against everyone else's shared 6,000.
                _trial_rate_rule(
                    "TrialRateLimitPerIp",
                    21,
                    aggregate_key_type="IP",
                    limit=TRIAL_LIMIT_PER_IP,
                    window_sec=TRIAL_WINDOW_PER_IP_ASN_SEC,
                ),
                _trial_rate_rule(
                    "TrialRateLimitPerAsn",
                    22,
                    aggregate_key_type="CUSTOM_KEYS",
                    limit=TRIAL_LIMIT_PER_ASN,
                    window_sec=TRIAL_WINDOW_PER_IP_ASN_SEC,
                    custom_keys=[waf.CfnWebACL.RateBasedStatementCustomKeyProperty(asn={})],
                ),
                _trial_rate_rule(
                    "TrialRateLimitAll",
                    23,
                    aggregate_key_type="CONSTANT",
                    limit=TRIAL_LIMIT_ALL,
                    window_sec=TRIAL_WINDOW_ALL_SEC,
                ),
                # Typed-question rate limit (module docstring): before the aggregate rule, for the same reason.
                _assistant_rate_rule(),
                # Aggregate (all-clients-combined) rate limit — see module
                # docstring. Evaluated after the managed rule sets and before
                # nothing (last): this and RateLimitPerIp are independent
                # bounds, not a priority-ordered fallback of one another.
                waf.CfnWebACL.RuleProperty(
                    name="AggregateRateLimit",
                    priority=25,
                    action=waf.CfnWebACL.RuleActionProperty(block={}),
                    statement=waf.CfnWebACL.StatementProperty(
                        rate_based_statement=waf.CfnWebACL.RateBasedStatementProperty(
                            aggregate_key_type="CONSTANT",
                            limit=AGGREGATE_RATE_LIMIT_PER_5MIN,
                            evaluation_window_sec=300,
                            # Required by the real WAFv2 API whenever
                            # aggregate_key_type="CONSTANT" -- see the module
                            # docstring's FIX paragraph. CDK's own type marks
                            # this optional; AWS's API does not.
                            scope_down_statement=_match_all_statement(),
                        )
                    ),
                    visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="AggregateRateLimit",
                        sampled_requests_enabled=True,
                    ),
                ),
            ],
        )

        # ── CloudFront Distribution ────────────────────────────────────────────
        # Resolve the origin-verify secret from us-east-1 (this stack's region) by
        # NAME. api_stack replicates pyvar/<env>/cf-origin-verify into us-east-1;
        # resolving by name emits {{resolve:secretsmanager:<name>:...}} which
        # Secrets Manager resolves in-region against the replica. (A name->ARN
        # lookup via from_secret_name_v2 builds a suffix-less ARN that Secrets
        # Manager cannot resolve; a eu-west-1 ARN is not resolvable cross-region.)
        # origin_verify_secret is retained to express the cross-stack deploy order.
        origin_verify_value = cdk.SecretValue.secrets_manager(
            f"pyvar/{cfg.env_name}/cf-origin-verify"
        ).unsafe_unwrap()

        # ALB as HTTP origin on port 80 (CloudFront handles TLS termination at edge).
        # Port 80 is used — not 443 — because CloudFront verifies origin certs against
        # the ALB DNS hostname, which is not covered by the pyvar.com ACM certificate
        # on the HTTPS:443 listener.  Traffic stays on the AWS backbone (not public
        # internet).  The ALB's HTTP:80 listener enforces the X-Origin-Verify header,
        # providing the same bypass-prevention as before.
        alb_origin = origins.HttpOrigin(
            alb_dns,
            protocol_policy=cf.OriginProtocolPolicy.HTTP_ONLY,
            http_port=80,
            origin_id="AlbOrigin",
            custom_headers={
                "X-Origin-Verify": origin_verify_value,
            },
        )

        # HSTS response header — prerequisite for HSTS preload eligibility
        # (hstspreload.org) on www.pyvar.com specifically. Note the scope
        # limit: pyvar.com's bare apex is served entirely by Aruba's own
        # forwarding proxy (a 301 to www.pyvar.com, outside CloudFront/this
        # stack's control — see the certificate comment below), so this
        # header can only ever cover www.pyvar.com and cannot close the
        # first-visit-to-the-bare-apex plaintext window; that would need a
        # separate, operator-only check of whether Aruba's forwarding
        # service supports custom response headers at all (uncertain, not
        # actioned here). max_age=1 year + includeSubDomains + preload are
        # the exact three hstspreload.org submission requirements.
        hsts_policy = cf.ResponseHeadersPolicy(
            self,
            "HstsPolicy",
            response_headers_policy_name=f"pyvar-{cfg.env_name}-hsts",
            security_headers_behavior=cf.ResponseSecurityHeadersBehavior(
                strict_transport_security=cf.ResponseHeadersStrictTransportSecurity(
                    access_control_max_age=cdk.Duration.days(365),
                    include_subdomains=True,
                    preload=True,
                    override=True,
                ),
            ),
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

        # Origin request policy for the trial path only. CloudFront adds `CloudFront-Viewer-ASN` to an origin
        # request only when an origin request policy names it (the default behaviour's managed policy does
        # not), and the API's per-network share (L5) reads it. An allow-list, not "all viewer headers": the lane
        # reads the User-Agent, the plugin's X-Pyvar-Client label and that header, nothing else; Authorization
        # is forwarded because api_cache_policy keys on it, as for every other route.
        trial_origin_request_policy = cf.OriginRequestPolicy(
            self,
            "TrialOriginRequestPolicy",
            origin_request_policy_name=f"pyvar-{cfg.env_name}-trial-origin",
            comment="Forwards the viewer network (ASN) to the no-sign-up trial lane",
            header_behavior=cf.OriginRequestHeaderBehavior.allow_list(
                "User-Agent",
                "X-Pyvar-Client",
                "CloudFront-Viewer-ASN",
            ),
            query_string_behavior=cf.OriginRequestQueryStringBehavior.none(),
            cookie_behavior=cf.OriginRequestCookieBehavior.none(),
        )

        # ── ACM Certificate (us-east-1, CloudFront alternate domain names) ────
        # DNS-validated TLS certificate for cfg.edge_domain_names (config.py)
        # as CloudFront aliases. Only provisioned when this environment has
        # aliases to serve at all — an environment with none (see the "prod"
        # override in config.py, pending a deliberate domain cutover) has
        # nothing to attach a cert to, and skipping it avoids provisioning +
        # DNS-validating a certificate for no reason. pyvar.com DNS stays
        # hosted at Aruba (P8 Task 7 decision — DNSSEC was never actually
        # activated there, despite being carried forward in earlier lead
        # prompts as if it had been; Route53 migration was assessed and
        # explicitly declined) — hosted_zone_id stays empty and the Route53
        # block below stays unused. On first deploy of an environment WITH
        # aliases, CloudFormation blocks here until the CNAME record(s) are
        # added manually to the pyvar.com zone at Aruba. After "cdk deploy"
        # starts, retrieve the required records with:
        #
        #   aws acm describe-certificate \
        #     --certificate-arn <CfnOutput: CloudFrontCertificateArn> \
        #     --region us-east-1 \
        #     --query "Certificate.DomainValidationOptions[*].{Name:ResourceRecord.Name,Value:ResourceRecord.Value}"
        #
        # These are subdomain-scoped validation CNAMEs (_<hash>.pyvar.com) —
        # they do not conflict with the existing apex A/MX records. Mirrors
        # the AlbCertificate pattern already proven in api_stack.py (eu-west-1,
        # P6) — same manual-CNAME-at-Aruba workflow.
        #
        # Note: making the bare apex (pyvar.com, no subdomain) itself resolve
        # to CloudFront is a separate concern from this certificate. A plain
        # CNAME cannot coexist with the apex's existing A/MX/NS records per
        # DNS spec — Aruba needs an ALIAS/ANAME-equivalent feature for that
        # step, or an apex-forwarding mechanism. www.pyvar.com has no such
        # constraint (already a CNAME today). Confirm Aruba's apex-aliasing
        # support before adding the apex-facing record.
        # TLS-floor tradeoff when edge_domain_names is empty (prod/staging
        # right now — see config.py): with no custom domain there's no ACM
        # certificate, and CloudFront only honors a custom
        # minimum_protocol_version when the distribution has one. The
        # minimum_protocol_version=TLS_V1_2_2021 set below is silently NOT
        # enforced in that case — CloudFront falls back to its shared default
        # certificate's fixed (older, non-configurable) TLS policy instead.
        # Acceptable for now because nothing points real traffic at this
        # distribution's default *.cloudfront.net address yet, but this is a
        # HARD PRECONDITION for the domain cutover (Stage C, tracked
        # separately): edge_domain_names must be non-empty — restoring a
        # custom cert and therefore this TLS floor — before pyvar.com is ever
        # pointed at this distribution.
        # cfg.certificate_arn (config.py) is an opt-in escape hatch for domain
        # cutover events (Stage C): CloudFront enforces alias uniqueness
        # account-wide, so pyvar.com/www.pyvar.com can't be added to THIS
        # distribution's Aliases while another distribution in the account
        # still holds them -- but ACM certificate issuance has no such
        # restriction, so the cert for the NEW aliases can be requested and
        # DNS-validated entirely out-of-band, well before the live cutover,
        # decoupling the (potentially slow, human-in-the-loop) DNS validation
        # wait from the actual alias-swap window. When set, this imports that
        # already-issued certificate by ARN instead of creating+validating a
        # new one inline -- every other environment (this field defaults to
        # "") is completely unaffected, same acm.Certificate(...) path as
        # before.
        cloudfront_certificate: acm.ICertificate | None = None
        if cfg.certificate_arn:
            cloudfront_certificate = acm.Certificate.from_certificate_arn(
                self, "CloudFrontCertificate", cfg.certificate_arn
            )
        elif cfg.edge_domain_names:
            cloudfront_certificate = acm.Certificate(
                self,
                "CloudFrontCertificate",
                domain_name=cfg.edge_domain_names[0],
                subject_alternative_names=cfg.edge_domain_names[1:],
                validation=acm.CertificateValidation.from_dns(),
            )

        self.distribution = cf.Distribution(
            self,
            "Distribution",
            comment=f"pyvar {cfg.env_name} CDN",
            domain_names=cfg.edge_domain_names or None,
            certificate=cloudfront_certificate,
            web_acl_id=web_acl.attr_arn,
            http_version=cf.HttpVersion.HTTP2_AND_3,
            # Only actually enforced when cloudfront_certificate is set — see
            # the comment above the certificate block.
            minimum_protocol_version=cf.SecurityPolicyProtocol.TLS_V1_2_2021,
            price_class=cf.PriceClass.PRICE_CLASS_100,  # US + Europe PoPs only — cheapest
            default_behavior=cf.BehaviorOptions(
                origin=alb_origin,
                viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=api_cache_policy,
                allowed_methods=cf.AllowedMethods.ALLOW_ALL,
                origin_request_policy=cf.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                response_headers_policy=hsts_policy,
                compress=True,
            ),
            additional_behaviors={
                # Health check: never cached, always passes through
                "/health": cf.BehaviorOptions(
                    origin=alb_origin,
                    viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cf.CachePolicy.CACHING_DISABLED,
                    allowed_methods=cf.AllowedMethods.ALLOW_GET_HEAD,
                    response_headers_policy=hsts_policy,
                ),
                # No-sign-up trial lane: same cache policy as the default behaviour (POSTs are not
                # cached; Authorization is in the key), but its own origin request policy so the API
                # receives the viewer's network.
                TRIAL_PATH_PATTERN: cf.BehaviorOptions(
                    origin=alb_origin,
                    viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=api_cache_policy,
                    allowed_methods=cf.AllowedMethods.ALLOW_ALL,
                    origin_request_policy=trial_origin_request_policy,
                    response_headers_policy=hsts_policy,
                    compress=True,
                ),
                # API docs: cache for 5 minutes
                "/docs": cf.BehaviorOptions(
                    origin=alb_origin,
                    viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cf.CachePolicy.CACHING_OPTIMIZED,
                    allowed_methods=cf.AllowedMethods.ALLOW_GET_HEAD,
                    response_headers_policy=hsts_policy,
                ),
            },
            enable_logging=True,
            log_includes_cookies=False,
        )

        # enable_logging=True makes CDK create the log bucket itself, as a child of the distribution called
        # "LoggingBucket", with no lifecycle rule: access logs (client IP addresses, URLs) were kept
        # forever. Adding the rule to that same bucket changes only its LifecycleConfiguration: no
        # replacement, nothing about the distribution. The rule also removes objects already older than the
        # limit, once. Looked up by CDK's own child id, so a CDK release that renames it fails the synth here
        # (and tests/test_cdk_access_log_retention.py) instead of silently dropping the rule.
        log_bucket = self.distribution.node.try_find_child("LoggingBucket")
        if not isinstance(log_bucket, s3.Bucket):
            raise RuntimeError(
                "CloudFront's access-log bucket was not found as 'LoggingBucket': the retention rule "
                "cannot be attached (see ACCESS_LOG_RETENTION_DAYS)"
            )
        log_bucket.add_lifecycle_rule(
            id="expire-access-logs",
            enabled=True,
            expiration=Duration.days(ACCESS_LOG_RETENTION_DAYS),
        )

        # P7 Task 6: without this, CloudFront's "Additional metrics" (CacheHitRate,
        # OriginLatency, and per-status-code error rate breakdowns — up to 8 metrics)
        # never reach CloudWatch at all, regardless of traffic volume. Billed as
        # CloudWatch custom metrics (~$0.30/metric/month, us-east-1) — up to ~$2.40/
        # month for this distribution. Needed to actually measure the release plan's
        # >60% cache-hit-rate target now that api/routes/var.py sets Cache-Control.
        cf.CfnMonitoringSubscription(
            self,
            "MonitoringSubscription",
            distribution_id=self.distribution.distribution_id,
            monitoring_subscription=cf.CfnMonitoringSubscription.MonitoringSubscriptionProperty(
                realtime_metrics_subscription_config=(
                    cf.CfnMonitoringSubscription.RealtimeMetricsSubscriptionConfigProperty(
                        realtime_metrics_subscription_status="Enabled",
                    )
                ),
            ),
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

        # ── Trial lane: edge alarm (us-east-1) ────────────────────────────────
        # A CloudFront web ACL's metrics are in us-east-1 under AWS/WAFV2, dimensioned by the ACL's metric
        # name (`WebACL`) and the rule's metric name (`Rule`); there is no `Region` dimension for CloudFront
        # (AWS's metric reference: "Required for all protected resource types except for Amazon CloudFront
        # distributions"). The alarm and its SNS topic therefore live here, not in the alerts stack. The topic
        # is created without subscribers, like the alerts topic: add one after deploy.
        self.edge_alerts_topic = sns.Topic(
            self,
            "EdgeAlertsTopic",
            topic_name=f"pyvar-{cfg.env_name}-edge-alerts",
            display_name=f"pyvar {cfg.env_name} edge alerts",
        )
        trial_blocks = cloudwatch.MathExpression(
            expression=" + ".join(f"m{i}" for i in range(len(TRIAL_RATE_RULE_METRICS))),
            label="Trial lane requests blocked by WAF",
            period=Duration.minutes(5),
            using_metrics={
                f"m{i}": cloudwatch.Metric(
                    namespace="AWS/WAFV2",
                    metric_name="BlockedRequests",
                    dimensions_map={"WebACL": f"pyvar-{cfg.env_name}-waf", "Rule": rule},
                    statistic="Sum",
                    period=Duration.minutes(5),
                )
                for i, rule in enumerate(TRIAL_RATE_RULE_METRICS)
            },
        )
        trial_blocks_alarm = cloudwatch.Alarm(
            self,
            "TrialWafBlocksAlarm",
            alarm_name=f"pyvar-{cfg.env_name}-trial-waf-blocks",
            alarm_description=(
                "The WAF blocked more than 1,000 no-sign-up trial requests in 5 minutes: a flood on "
                "/api/v1/trial/, or real callers being refused. See docs/plan-trial-lane-throttle.md "
                "(Operations): scripts/trial_ctl.py attack on, or TrialKillSwitch."
            ),
            metric=trial_blocks,
            threshold=TRIAL_WAF_BLOCKS_ALARM_THRESHOLD,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        trial_blocks_alarm.add_alarm_action(cw_actions.SnsAction(self.edge_alerts_topic))

        # ── Outputs ───────────────────────────────────────────────────────────
        # Stored on self (not just a bare CfnOutput) so pipeline_stack.py's
        # ProdSmokeTest step (#172) can wire it via env_from_cfn_outputs —
        # a `post` step of the SAME stage this EdgeStack belongs to, so
        # unlike _migration_step's `pre`-step problem, referencing this
        # stage's own output here is a genuine, non-cyclic dependency.
        self.cloudfront_domain_output = cdk.CfnOutput(
            self, "CloudFrontDomain", value=self.distribution.distribution_domain_name
        )
        cdk.CfnOutput(self, "CloudFrontId", value=self.distribution.distribution_id)
        cdk.CfnOutput(
            self,
            "CloudFrontCertificateArn",
            value=cloudfront_certificate.certificate_arn if cloudfront_certificate else "none",
        )
