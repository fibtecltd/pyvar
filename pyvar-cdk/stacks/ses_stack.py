"""
stacks/ses_stack.py — SES domain identity for transactional email (#149)

Reasoning:
- Verification emails (api/routes/auth.py::send_verification_email) had no
  real transport — a structured-log stub since P8 Task 3. That was
  deliberately deferred pending pyvar.com's DNS hosting decision (P8 Task 7);
  #158 resolved that (Aruba stays, www.pyvar.com live), so this can proceed.
- Verifies the pyvar.com domain identity ITSELF, not a subdomain — simpler,
  one less moving part, and reasonable pre-launch (a dedicated subdomain
  mainly isolates sending reputation, which matters at real send volume more
  than it does here). Easy DKIM's 3 CNAME records live at
  <selector>._domainkey.pyvar.com — a different name than the bare apex, so
  this is entirely unaffected by #158's broken apex A/MX forwarding.
- The CNAME records themselves must be added MANUALLY at Aruba (DNS stays
  there — see #158) — the same "CDK sets up the mechanism, one manual DNS
  step is needed" pattern already used for the ACM certificate validation
  record in api_stack.py. Read them from this stack's CfnOutputs after
  deploy.
- Starts in SES *sandbox* mode (the AWS default for any new account/region):
  only individually pre-verified recipient addresses can receive mail until
  an operator requests production access via an AWS Support case — a
  console/account-level action, not something CDK/IaC can request on its own.
- Deployed in the same region as the API (eu-west-1, not edge_stack.py's
  us-east-1) — SES sending has no CloudFront/edge dependency, and this keeps
  the identity in the same region as the ECS task that calls SendEmail.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import Stack
from aws_cdk import aws_ses as ses
from constructs import Construct

from config import PyvarConfig


class SesStack(Stack):

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        cfg: PyvarConfig,
        configuration_set: ses.IConfigurationSet | None = None,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)

        # Easy DKIM, 2048-bit, dkim_signing=True (all defaults) — no
        # mail_from_domain override, so bounces/complaints route through
        # SES's own amazonses.com MAIL FROM rather than provisioning a
        # dedicated MAIL FROM subdomain + its own MX record for an MVP
        # transactional flow.
        #
        # configuration_set (ses_events_stack.py) is set as this identity's
        # DEFAULT — every send from this identity (api/routes/auth.py's
        # existing send_email call, unmodified) automatically gets
        # bounce/complaint event tracking with no application code change.
        self.email_identity = ses.EmailIdentity(
            self,
            "EmailIdentity",
            identity=ses.Identity.domain(cfg.domain_name),
            configuration_set=configuration_set,
        )

        # api_stack.py grants ses:SendEmail/SendRawEmail against this ARN —
        # exposed so that stack can wire it without a second lookup.
        self.identity_arn = self.email_identity.email_identity_arn

        for i, record in enumerate(self.email_identity.dkim_records, start=1):
            cdk.CfnOutput(
                self,
                f"DkimRecord{i}",
                value=f"CNAME {record.name} -> {record.value}",
                description=(
                    f"DKIM record {i} of 3 — add as a CNAME in the pyvar.com zone at "
                    "Aruba (DNS stays there per #158; this name is not the bare apex, "
                    "so it does not touch the existing A/MX records)."
                ),
            )

        cdk.CfnOutput(
            self,
            "SesSandboxNote",
            value=(
                "New SES identities start in sandbox mode: only individually "
                "pre-verified recipient addresses can receive mail. Request "
                "production access via an AWS Support case (Service Quotas > SES "
                "sending limits) before relying on this for real user registrations."
            ),
        )
