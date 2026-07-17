# P7 Task 7 — AWS Cost Explorer review

Period reviewed: 2026-07-01 to 2026-07-17 (month-to-date, `Estimated: true`
per Cost Explorer — current-month data isn't fully finalized yet).

## Headline finding — the $250 budget is healthy today only because of a
## temporary credit; the gross run-rate would breach it

`aws budgets describe-budgets` shows `pyvar-dev-monthly` (limit **$250**,
`IncludeCredit: true`) at **$175.89 actual spend**, `HealthStatus: HEALTHY`.
That looks comfortable at 17/31 days into the month (~55% of the month,
~70% of budget consumed) — but digging into *why* it's that low:

`aws ce get-cost-and-usage --group-by RECORD_TYPE` for this period:

| Record type | Amount |
|---|---|
| Usage (gross) | **$220.77** |
| Tax | $29.31 |
| Credit | **-$75.88** |
| **Net** | **$174.20** (matches the budget's $175.89 closely, small rounding/timing) |

A **-$75.88 credit** is currently offsetting ~34% of gross usage. This
shows up concretely in the per-service breakdown: `aws rds
describe-db-clusters` confirms Aurora has been running since 2026-06-22
(creating real, substantial usage — 384.6 ACU-Hr, 4.36M IOs this period
alone), yet Cost Explorer's `Amazon Relational Database Service` line for
this period is **~$0** — the credit is being applied specifically against
Aurora's charges, not spread evenly.

**Extrapolating the gross run-rate** (not the credited net) to a full
31-day month: $220.77 usage ÷ 17 × 31 ≈ **$402/month gross**, or including
tax and excluding the credit, ≈ **$390-410/month** — well over the $250
budget and the release plan's <£150/month (~$190 at typical GBP/USD) target.
**If this credit is one-time/promotional and doesn't recur next billing
cycle, the account is on track to breach both the AWS Budget and the
release-plan cost target**, even though today's dashboard looks green.

Could not determine the credit's exact program/expiry via CLI (Cost
Explorer's `RECORD_TYPE=Credit` breakdown doesn't expose the promotional
credit's name or expiry date — that needs the Billing Console's "Credits"
page). **Recommend checking the Billing Console directly** to confirm
whether this credit recurs monthly or is a one-time/limited allocation
before treating the current "HEALTHY" budget status as durable.

## Top 3 cost drivers (by gross service-level spend, this period)

| Rank | Service | Amount (17 days) | Extrapolated /month |
|---|---|---|---|
| 1 | Amazon Virtual Private Cloud | $48.01 | ~$87 |
| 2 | Amazon ElastiCache | $32.68 | ~$59 |
| 3 | EC2 - Other (NAT Gateway) | $19.03 | ~$35 |

### 1. Amazon VPC — $48.01 (17d) / ~$87/month

**Driving it**: `EU-VpcEndpoint-Hours` = $42.24 (88% of this line) +
`EU-PublicIPv4:InUseAddress` = $5.77. Confirmed via `network_stack.py`: 5
Interface VPC Endpoints (SQS, ECR, ECR_DOCKER, Secrets Manager, CloudWatch
Logs) × `vpc_max_azs=2` = 10 endpoint-AZ combinations × $0.01/hr × 24h ×
17d ≈ $40.80 — matches the observed $42.24 closely. (S3 already uses the
free Gateway endpoint, not billed here.)

**Expected or inefficiency?** The endpoints themselves are the right
architectural choice (keeps SQS/ECR/Secrets Manager/CloudWatch Logs traffic
off the public internet, per CLAUDE.md's network design). But running them
across **2 AZs in a dev environment that doesn't need multi-AZ HA** is a
genuine, specific inefficiency — `pyvar-cdk/config.py` already applies this
exact "no HA tradeoff for non-prod" reasoning to `vpc_nat_gateways` (1 for
dev, 2 for prod, with a comment saying so) but not to `vpc_max_azs`, which
is a flat `2` regardless of environment.

**Mitigation**: reduce `vpc_max_azs` to 1 for dev specifically (mirroring
the existing per-env NAT Gateway pattern), roughly halving the
`VpcEndpoint-Hours` line to ~$21/17d (~$38/month) — an estimated **~$21/17
days (~$38/month) saving**. Not implemented here (read-only review task);
this would need `cdk deploy` and should be scoped carefully since
`vpc_max_azs` likely affects subnet layout for Aurora/ElastiCache subnet
groups too (both currently span 2 AZs) — a bigger change than a one-line
config tweak, flagging for a follow-up task rather than doing it now.

### 2. Amazon ElastiCache — $32.68 (17d) / ~$59/month

**Driving it**: `EU-CachedData:Redis` — the entire line is ElastiCache
Serverless's data/ECPU consumption charge, all under one usage type (no
separate storage vs. compute breakdown at this granularity).

**Expected or inefficiency?** Serverless's billing model has a minimum
floor that doesn't scale down to near-zero for a low-traffic dev
environment the way, say, Aurora's `min_acu=0.5` does — but the *absolute*
number here (~$59/month extrapolated) is **~4.5x the release plan's ~£10
(~$13)/month ElastiCache target**, more than a rounding difference.

**Mitigation**: worth evaluating whether a small **provisioned**
single-node cache (e.g. `cache.t4g.micro`, ~$0.016/hr ≈ ~$11.68/month in
`eu-west-1`) would actually be cheaper than Serverless's floor for this
specific low/spiky dev traffic pattern — Serverless is optimized for
variable/unpredictable load, but dev's load here is consistently *very*
low, which is exactly the profile where a small fixed-size node can beat
Serverless's minimum billing. Not implemented here — switching cache
architecture is a bigger decision than a config tweak and should be a
deliberate follow-up, not a reflexive change during a cost review.

### 3. EC2 - Other (NAT Gateway) — $19.03 (17d) / ~$35/month

**Driving it**: `EU-NatGateway-Hours` = $18.43 (97% of this line) — a
single NAT Gateway running 24/7 (flat hourly charge regardless of traffic;
$18.43 ÷ (24×17) ≈ $0.045/hr, matches `eu-west-1` NAT Gateway pricing for
one gateway).

**Expected or inefficiency? Already near-optimal.** `pyvar-cdk/config.py`
already sets `vpc_nat_gateways=1` for dev with an explicit comment ("1 NAT
GW saves ~£27/month vs 2, no HA tradeoff for non-prod") vs. `2` for prod —
this is the cost-conscious choice already made deliberately, not an
oversight. Further reduction would mean eliminating the NAT Gateway
entirely, which is only safe if nothing in the private subnets needs
generic internet egress not covered by a VPC endpoint (Sentry SDK calls to
`sentry.io`, PyPI/OS package pulls during EC2 UserData bootstrap, etc. are
plausible candidates that still need it). **Not confirmed either way in
this review** — flagging as a bigger, separate investigation
("does anything actually still need NAT once VPC endpoints cover
SQS/ECR/Secrets Manager/CloudWatch Logs and S3?"), not a same-task fix.

## Summary

| Driver | Status | Action |
|---|---|---|
| Temporary credit masking true run-rate | **Needs attention** | Check Billing Console for credit expiry/recurrence before trusting current budget health |
| VPC endpoints across 2 AZs in dev | Genuine inefficiency, ~$38/month recoverable | Follow-up: `vpc_max_azs=1` for dev (needs care re: subnet groups) |
| ElastiCache Serverless cost vs. target | Real mechanism, but 4.5x over the £10/month target | Follow-up: evaluate a small provisioned node for dev |
| NAT Gateway (single, dev) | Already near-optimal | No action — already the deliberate low-cost choice; further reduction needs a separate "is NAT still needed at all" investigation |
