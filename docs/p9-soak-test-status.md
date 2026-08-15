# pyvar-prod post-migration soak test — COMPLETE, torn down

**Status: soak test itself finished 2026-08-13T17:33Z, all temporary AWS
resources deleted and confirmed gone. Since then this doc has picked up a
second life tracking the observability gaps the soak test surfaced (no
Sentry, no prod alerts/dashboard) through to resolution — see "Observability
rollout" below. That work is now fully closed out: Sentry verified in both
environments, prod alerts/dashboard deployed and confirmed real, both
environments' alert-topic email subscriptions confirmed. No open items.**

Not committed infra — this doc records what was stood up directly via AWS
CLI (not CDK) for a time-boxed 48h validation window, so a fresh session
picking this up mid-window wouldn't have to re-derive resource names or
re-check whether setup already happened. That need has now passed.

## Why

Aurora prod's Alembic migration (`0005_user_email_suppression`) was applied
and verified directly against the database on 2026-08-10. Prod has received
zero real traffic so far (DNS hasn't cut over — see
`docs/domain-cutover-stage-b-c-plan.md`). This soak test exercises prod's
API continuously for 48h to build confidence before any future domain
cutover, using the existing smoke-test logic (health check + unauthenticated
compute endpoint expecting 401) that the CDK pipeline already runs once per
deploy — just repeated on a schedule instead of once.

## What was validated first (2026-08-11)

- `aws sts get-caller-identity` confirmed real credentials, account
  `347228921290`.
- **Dev's CloudWatch monitoring is genuinely populated**: `pyvar-dev-overview`
  dashboard exists (`AWS/ApplicationELB` RequestCount/5xx/TargetResponseTime,
  `AWS/SQS` queue depth, `AWS/AutoScaling`, `AWS/ElastiCache`). Pulled real
  data directly (not just confirmed the dashboard renders): ~50-60
  requests/15min, 0 `5xx`, p95 latency 10-70ms over a 6h window — real,
  healthy signal from dev's live traffic. CloudWatch is trustworthy for
  this soak test.
- **Sentry is not configured anywhere in this account** — checked both
  `pyvar-dev-api` and `pyvar-prod-api` ECS task definitions directly
  (`describe-task-definition`): no `SENTRY_DSN` env var or secret wired into
  either. No Secrets Manager or SSM entries mentioning "sentry" exist either.
  This matches CLAUDE.md §7's documented convention ("SENTRY_DSN leave blank
  in dev") but confirms it's blank in **prod too** — not yet turned on
  anywhere, not something broken. **This soak test's error signal is
  CloudWatch-only; there is no Sentry project to check.** Worth a separate
  decision later on whether Sentry should be turned on for prod.
- Prod has **no `observability`/`alerts` CDK stack deployed** (checked via
  `list-stacks`) — only dev does. Same "not part of the pipeline-managed
  stage set, deployed separately" category as `pyvar-prod-ami`. This is why
  the soak test queries `AWS/ApplicationELB`/`AWS/Lambda` metrics directly
  via `get-metric-statistics` rather than reading a prod dashboard — the
  underlying metrics exist regardless of whether a Dashboard resource does;
  only the visualization/alarms are missing for prod.

## What was stood up (AWS CLI, not CDK — temporary, 48h)

| Resource | Name / ARN |
|---|---|
| Lambda function | `pyvar-prod-soak-smoketest` — `arn:aws:lambda:eu-west-1:347228921290:function:pyvar-prod-soak-smoketest` |
| IAM role | `pyvar-prod-soak-test-lambda-role` — `arn:aws:iam::347228921290:role/pyvar-prod-soak-test-lambda-role` (basic execution only, no VPC — calls the public CloudFront domain over the internet) |
| EventBridge rule | `pyvar-prod-soak-test-schedule` — `arn:aws:events:eu-west-1:347228921290:rule/pyvar-prod-soak-test-schedule`, `rate(5 minutes)`, `ENABLED` |
| Lambda log group | `/aws/lambda/pyvar-prod-soak-smoketest` |

All 3 tagged `Purpose=pyvar-prod-soak-test`, `Temporary=true`.

**What the Lambda does** (source kept at `/tmp/soak_lambda/handler.py` in the
session that created it, not committed to the repo — reproduce from this
doc if needed): `GET https://d31t9sn2oya6qy.cloudfront.net/health` expecting
`200`, then `POST https://d31t9sn2oya6qy.cloudfront.net/api/v1/var/compute`
expecting `401` (unauthenticated — matches `api/middleware/auth.py`'s
`HTTPBearer` rejection, same pattern as the CDK pipeline's own dev smoke
test). Raises on any mismatch, which surfaces as an `AWS/Lambda` `Errors`
metric — no custom metric or Sentry needed for aggregate error tracking.

Manual invoke confirmed working before the schedule was wired up:
`{"health": 200, "unauth_compute": 401}`, `StatusCode: 200`.

**Prod's CloudFront domain** as of setup: `d31t9sn2oya6qy.cloudfront.net`
(hardcoded into the Lambda — re-verify via `aws cloudformation
describe-stacks --stack-name pyvar-prod-edge --region us-east-1` if
`pyvar-prod-edge` is ever recreated, since the domain would change).

## Window

- **Start**: 2026-08-11T17:27:20Z
- **End (48h)**: 2026-08-13T17:27:20Z

## How to check results (aggregates, not raw logs)

```bash
# Invocation / error counts (the primary aggregate signal)
aws cloudwatch get-metric-statistics --region eu-west-1 \
  --namespace AWS/Lambda --metric-name Invocations \
  --dimensions Name=FunctionName,Value=pyvar-prod-soak-smoketest \
  --start-time <window-start> --end-time <now> --period 3600 --statistics Sum

aws cloudwatch get-metric-statistics --region eu-west-1 \
  --namespace AWS/Lambda --metric-name Errors \
  --dimensions Name=FunctionName,Value=pyvar-prod-soak-smoketest \
  --start-time <window-start> --end-time <now> --period 3600 --statistics Sum

# Prod ALB signal directly (no dashboard exists for prod, query the metrics
# that would back one — same namespace pyvar-dev-overview already proved out)
aws cloudwatch get-metric-statistics --region eu-west-1 \
  --namespace AWS/ApplicationELB --metric-name HTTPCode_Target_5XX_Count \
  --dimensions Name=LoadBalancer,Value=app/pyvar-prod-alb/23e72819df228329 \
  --start-time <window-start> --end-time <now> --period 3600 --statistics Sum
```

No Sentry project to check (see above — not configured in this account).

## Teardown (do this at the 48h check-in, or sooner if aborted early)

```bash
aws events remove-targets --rule pyvar-prod-soak-test-schedule --ids 1 --region eu-west-1
aws events delete-rule --name pyvar-prod-soak-test-schedule --region eu-west-1
aws lambda delete-function --function-name pyvar-prod-soak-smoketest --region eu-west-1
aws iam detach-role-policy --role-name pyvar-prod-soak-test-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam delete-role --role-name pyvar-prod-soak-test-lambda-role
aws logs delete-log-group --log-group-name /aws/lambda/pyvar-prod-soak-smoketest --region eu-west-1
```
Then delete this file (or update it with the final summary and leave it as a
record — user's call at teardown time).

## Check-in log

- **2026-08-11T17:27Z** — setup complete, manual invoke confirmed working.
  Three self-wakeup checks scheduled in the creating session: `80311fb4`
  (~17:43Z, setup+15min), `b540e550` (2026-08-12 ~17:31Z, ~24h),
  `82121219` (2026-08-13 ~17:33Z, 48h/teardown). **These are session-only —
  they die if this Claude session ends before firing.** If that happens,
  the AWS-side rule/Lambda keep running regardless (they're independent of
  any agent session), but the scheduled check-ins won't happen automatically
  — a fresh session (or the user) should re-check manually using the
  "How to check results" commands above, and must handle teardown manually
  at the 48h mark if the `82121219` job didn't survive to fire.
- **2026-08-11T17:43Z** (setup+15min, job `80311fb4`) — healthy, silent
  check-in: 5 real Lambda invocations across the last 20min (schedule is
  genuinely firing every 5min, not just the manual test), 0 Errors, 0 ALB
  5xx. No action needed.
- **2026-08-12T17:26Z** (~24h mark, ad-hoc user-requested check, not the
  scheduled `b540e550` job) — healthy: ~289 Lambda invocations over the
  elapsed ~24h (steady 12/hour = every 5min, no gaps), 0 Errors the entire
  window, 0 ALB 5xx, ALB p95 latency stable at 4-6ms throughout. No action
  needed.
- **2026-08-12T17:31Z** (~24h mark, scheduled job `b540e550`) — 24h clean:
  290 invocations total, 0 Errors, 0 ALB 5xx, p95 latency range 4.0-6.2ms
  the whole window. No action needed. Next: final 48h check-in/teardown
  (`82121219`), ~2026-08-13T17:33Z.
- **2026-08-13T16:17Z** (~47h mark, ad-hoc user-requested check) — still
  clean: 563 invocations total, 0 Errors, 0 ALB 5xx, p95 latency range
  4.2-6.2ms the whole window. No action needed. Final 48h check-in/teardown
  (`82121219`) due in ~1h15min.
- **2026-08-13T17:20Z** (~48h mark, ad-hoc user-requested check) — still
  clean: 576 invocations total, 0 Errors, 0 ALB 5xx, p95 latency range
  4.2-6.2ms the whole window. No action needed. Essentially at the 48h
  mark now — did not tear down yet since the scheduled final check-in
  (`82121219`, ~17:33Z) is only ~13min away and will do that automatically.
- **2026-08-13T17:33Z** (final check-in, job `82121219`, full 48h window
  2026-08-11T17:27:20Z → 2026-08-13T17:33:13Z) — **FINAL RESULT: clean
  the entire 48 hours.**
  - 579 Lambda invocations total, **0 Errors** — every single one of ~576
    scheduled 5-minute checks (plus the 3 manual/ad-hoc ones from earlier
    check-ins) returned `health=200` and `unauth_compute=401` as expected.
  - **0 ALB 5xx** for the entire window.
  - ALB p95 latency: 3.9-6.2ms range, no drift, no spikes, no degradation
    over 48h.
  - Teardown executed and verified: `pyvar-prod-soak-test-schedule` (rule),
    `pyvar-prod-soak-smoketest` (Lambda), `pyvar-prod-soak-test-lambda-role`
    (IAM role), and `/aws/lambda/pyvar-prod-soak-smoketest` (log group) all
    confirmed deleted via direct `describe`/`get` calls returning
    `ResourceNotFoundException`/`NoSuchEntity`/empty — nothing left behind.
  - **Conclusion**: prod's API, ALB, and (via the earlier direct DB
    verification on 2026-08-10) Aurora schema have held up cleanly under
    continuous synthetic traffic for 48h post-migration. No blockers found
    for whatever comes next (Stage B/C domain cutover planning, or turning
    on Sentry for prod — both still open, separate, not started).

## Observability rollout — Sentry + prod alerts/dashboard (2026-08-14 to 2026-08-15)

Follow-on to this soak test's own finding above ("Sentry is not configured
anywhere in this account" / "Prod has no `observability`/`alerts` CDK stack
deployed"). Both gaps are now closed.

### Sentry (PR #229, merged as `e8e76f8`, includes review-fix commits
`238ec90`/`c38bf85`)

- Single shared Sentry project; DSN stored as `pyvar/dev/sentry-dsn` and
  `pyvar/prod/sentry-dsn` in Secrets Manager (created directly by the user,
  never passed through chat — same handling as any other real secret).
- Workers (EC2): DSN fetched via `scripts/fetch-config.sh`, optional/
  non-blocking — a missing secret degrades to "no Sentry", never blocks
  worker boot.
- API (Fargate): DSN fetched at the **application layer**
  (`observability/setup.py::_resolve_sentry_dsn()`), not via ECS's native
  `secrets={}` — a review-fix commit (`c38bf85`) moved it off that
  mechanism specifically because ECS-native secret injection has no
  "optional" mode: a rotated/deleted secret would otherwise fail every new
  Fargate task launch outright and could block prod deploys entirely over
  an observability nice-to-have.
- Verified live, not just deployed: ECS Exec isn't enabled on this service,
  so verification used a one-off `aws ecs run-task` against each
  environment's real task definition (in-VPC, real network config) running
  the actual `setup_sentry()`/`_resolve_sentry_dsn()` code path and calling
  `sentry_sdk.capture_exception(...)`. Both task runs exited 0 and both
  events were confirmed received in the Sentry project by the user, tagged
  correctly:
  - dev: `CAPTURED_EVENT_ID=925117010ca748f7861a72b8d516a999`,
    `environment=dev`
  - prod: `CAPTURED_EVENT_ID=a8caaa09ecf34542b630ff0609d03723`,
    `environment=prod`
- Real-time Sentry alert rule scoped to `environment:production` set up by
  the user (separate from the pre-existing weekly digest) — covers the P9
  exit gate's 48h SEV-1 visibility requirement.

### Prod alerts + observability stacks (deployed 2026-08-15)

- `pyvar-prod-alerts`: `CREATE_COMPLETE` — SNS topic `pyvar-prod-alerts` +
  CloudWatch alarms (`WorkerErrorAlarm`, `ApiLatencyP95Alarm`,
  `Api5xxAlarm`, `SesSuppressionAlarm`).
- `pyvar-prod-observability`: `CREATE_COMPLETE` — dashboard
  `pyvar-prod-overview`
  (https://eu-west-1.console.aws.amazon.com/cloudwatch/home?region=eu-west-1#dashboards:name=pyvar-prod-overview).
- Dashboard confirmed **real, not just deployed**: queried the underlying
  CloudWatch metrics directly (not just checked the stack deployed) for the
  three widgets that predate this rollout — ALB RequestCount, 5xx, p95
  latency. All backed by genuine historical data from this soak test and
  the Day-3 smoke test: ~24 req/hour steady during the soak window, 0 5xx
  the entire time, single-digit-ms p95 with one real spike during the
  smoke test's heavier load. Current hours read 0 request count, which is
  expected — no live public traffic yet (domain cutover still on hold, see
  `docs/domain-cutover-stage-b-c-plan.md`).

### Email subscriptions — status as of 2026-08-15

| Topic | Endpoint | Status |
|---|---|---|
| `pyvar-dev-alerts` | `filippo.b@fibtec.co.uk` | **Confirmed** — already existed before this rollout, dev has not been unmonitored |
| `pyvar-prod-alerts` | `filippo.buchicchio@gmail.com` | **Confirmed** — click-through completed, verified directly via `aws sns get-subscription-attributes` (`PendingConfirmation: false`), not inferred from the subscribe call |

**Closed.** Both dev and prod alert topics have confirmed subscribers.
Prod alarm notifications (`WorkerErrorAlarm`, `ApiLatencyP95Alarm`,
`Api5xxAlarm`, `SesSuppressionAlarm`) now actually reach someone. No open
items remain from the observability rollout.
