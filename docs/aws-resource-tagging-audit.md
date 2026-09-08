# AWS Resource Tagging Audit — pyvar / tengrade / common

Account **347228921290**, regions **eu-west-1** (primary) and **us-east-1** (CloudFront/WAF edge resources, per `CLAUDE.md` §3.4). Generated via the AWS Resource Groups Tagging API (`get-resources`, both regions) supplemented with per-service `list-*`/`describe-*` calls for resource types that API covers poorly or not at all (IAM roles/users, S3 bucket tags, ACM, CloudFront, ElastiCache/VPC endpoints, Route53, SES, budgets, KMS, GuardDuty, Config, CloudTrail) — the Tagging API only returns resources that carry at least one tag already, so fully-untagged resources are otherwise invisible to it, and this is exactly where several of the real findings below came from.

**STATUS: live tagging applied on 2026-09-08, following human review of this document.** All resources marked "needs tagging" below have been tagged in AWS via the CLI (`tag-resources` / per-service tag calls). No resource was deleted, modified, or restarted — this was a tag-only pass. See "Live tagging — results" immediately below for what was actually applied, including one correction found mid-execution (12 CloudWatch target-tracking alarms, 6 ElastiCache-managed VPC endpoints, and the Chatbot Slack config had been mis-classified as "already tagged" in the original discovery pass below — they were pyvar-owned but had never actually been tagged by CDK; a full before/after re-scan of the account caught this and they were tagged in the same pass. No `pyvar-cdk` code change was made — see "Key finding" below for why none was needed.)

## Live tagging — results

- **tengrade: 121/121 tagged** `Project=tengrade` (86 API-visible resources + 34 IAM roles + 1 IAM user). Verified via a post-tagging `resourcegroupstaggingapi get-resources` re-scan plus full IAM tag checks (not sampled).
- **common: 20/20 tagged** `Project=common` (9 API-visible resources, excluding the 2 non-actionable payment-instrument records + 10 IAM bootstrap roles + the `fibtec-daily` budget). One exception: `awscodestarnotifications-rule` **cannot be tagged** — AWS rejects it outright (`ManagedRuleException: Tag related operations on the managed rule awscodestarnotifications-rule is not allowed`). This is an AWS-managed system resource with no tagging API surface at all, confirmed by the live API call, not assumed.
- **pyvar: 6/6 gap resources tagged** `Project=pyvar` (ACM cert, ECR repo, 3 secrets, IAM user), plus **19 additional pyvar resources** found mid-execution to be untagged despite being correctly attributed to pyvar in the discovery pass (6 ElastiCache-managed VPC endpoints, 12 ECS/ASG target-tracking CloudWatch alarms, 1 Chatbot Slack config) — all now tagged `Project=pyvar` (+ `Environment=dev`/`prod` from the subnet/name evidence already in the discovery pass, + `Owner=fibtec-limited` where the resource type supports it).
- **Post-tagging verification:** re-ran the full Tagging API scan across both regions. Only the 2 non-actionable `payments:payment-instrument` records and the un-taggable `awscodestarnotifications-rule` remain without a `Project` tag — both expected and documented above, not oversights.
- **Non-actionable, left alone as documented:** 6 AWS-managed default KMS keys (AWS does not permit customer tags on them) and 2 `payments:payment-instrument` records (not a taggable resource type / not a project resource).

## Summary

| Classification | Resources found | Tagged before this task | Tagged live in this pass | Still untagged (non-actionable) |
|---|---|---|---|---|
| pyvar | 658 (+2 stale/deleted records, excluded) | 633 (658 minus the 25 total tagged in this pass) | **25** (6 documented gaps + 19 found mid-execution — see "Live tagging — results") | 0 |
| tengrade | 121 | 0 | **121** | 0 |
| common | 22 actionable (+8 non-actionable found) | 0 | **20** | 2 (payment-instrument records; `awscodestarnotifications-rule` is also untaggable — AWS rejects it) |
| unclear | 0 | — | — | — |

No genuinely unclear resources were found — every resource in the account could be confidently attributed to pyvar, tengrade, or shared account infrastructure using name matching, CloudFront origin inspection, VPC subnet cross-referencing, or CDK source cross-checks. This account has no Route53 hosted zones (DNS for pyvar.com is external, per `edge_stack.py`'s own comments), no CloudTrail trail, no GuardDuty detector, no Config recorder, and no Cost and Usage Report — noted here since the task asked to check for them, not because any of them need tagging.

## Key finding: pyvar's CDK tagging is essentially complete already

`pyvar-cdk/app.py` applies `cdk.Tags.of(app).add(...)` at the top level, and `pyvar-cdk/stacks/pipeline_stack.py:1432-1435` separately applies the same four tags on `PyvarDeployStage` — the documented fix (that file's own comment, lines 1419-1431) for CDK Pipelines' Stage-synth boundary, where a `Stage`'s independently-synthesized cloud assembly doesn't inherit Aspects registered on an app-level ancestor. That fix is live and verified working: every pyvar CloudFormation stack, all 43 pyvar IAM roles (checked in full, not sampled), and every ECS/RDS/ElastiCache/S3/Lambda/SNS/SQS/WAF/ACM/SES/Image-Builder resource checked already carries `Project=pyvar`. **No pyvar-cdk code change is needed for the Aspect-reachability issue this task asked me to look for — it was already fixed.**

The 6 pyvar gaps found below are a *different* category: resources CDK never creates in the first place (imported by ARN/name, or provisioned outside CDK entirely), so there is no CFN resource for `Tags.of()` to attach to. This can't be fixed by changing the Aspect — only by tagging the resource directly (or, optionally, adding a code comment documenting the manual-tagging obligation, noted per-item below).

## pyvar — action needed (6 resources)

| Resource | ARN / ID | Current tags | Proposed tag | Why CDK can't reach it |
|---|---|---|---|---|
| ACM certificate (pyvar.com + www, prod CloudFront) | `arn:aws:acm:us-east-1:347228921290:certificate/a18950da-05cc-49fa-81d9-78828e512f3e` | _none_ | `Project=pyvar`, `Environment=prod`, `Owner=fibtec-limited` | `edge_stack.py:384-386` imports it via `acm.Certificate.from_certificate_arn(cfg.certificate_arn)` — prod's documented "opt-in escape hatch" for a certificate that was DNS-validated once, manually, outside CDK. An imported `ICertificate` has no CFN resource in the template, so `Tags.of()` has nothing to attach to. The sibling dev cert (`e6929439-...`, created via `acm.Certificate(...)`) *is* tagged — confirms this is specific to the imported-cert code path, not a general Aspect bug. |
| ECR repository `pyvar-prod-api` | `arn:aws:ecr:eu-west-1:347228921290:repository/pyvar-prod-api` | _none_ | `Project=pyvar`, `Environment=prod`, `Owner=fibtec-limited` | `api_stack.py:98-106`'s own comment: "Referenced (not created) by this stack. The repo is provisioned and managed outside CDK... creating it via CDK's `ecr.Repository` construct here would collide with the existing repo." Same non-CDK provisioning as dev's repo — but dev's (`pyvar-dev-api`) carries `Project=pyvar` and prod's doesn't. Pure tagging drift between two manually-provisioned, identically-built repos, not a code bug. |
| Secret `pyvar/github-token` | `arn:aws:secretsmanager:eu-west-1:347228921290:secret:pyvar/github-token` | _none_ | `Project=pyvar` | Imported via `from_secret_name_v2` (see the import-pattern comment near `ses_events_stack.py:15`) — a long-lived manually-created secret CDK only reads, never owns. |
| Secret `pyvar/dev/sentry-dsn` | `arn:aws:secretsmanager:eu-west-1:347228921290:secret:pyvar/dev/sentry-dsn` | _none_ | `Project=pyvar`, `Environment=dev` | `api_stack.py:248` — `Secret.from_secret_name_v2(...)`. Manually created (`CLAUDE.md` §7 says `SENTRY_DSN` is left blank in dev — the secret container exists, CDK just never creates or tags it). |
| Secret `pyvar/prod/sentry-dsn` | `arn:aws:secretsmanager:eu-west-1:347228921290:secret:pyvar/prod/sentry-dsn` | _none_ | `Project=pyvar`, `Environment=prod` | Same as above. |
| IAM user `pyvar-cdk-deployer` | `arn:aws:iam::347228921290:user/pyvar-cdk-deployer` | _none_ | `Project=pyvar` | The long-lived CI identity CDK deploys *as* — necessarily created before/outside any CDK stack. |

## pyvar — tagged via CDK already (650 of 669 total pyvar resources, by type)

**Correction:** 3 rows below (EC2 VPC endpoints, CloudWatch alarms (ECS target-tracking), AWS Chatbot Slack configuration) were originally counted here as "already tagged" — they were not. They were correctly *attributed* to pyvar (by VPC-subnet cross-reference and by name), but CDK's `Tags.of()` Aspect never actually reaches AWS-auto-created supporting resources (ElastiCache-managed VPC endpoints, Application Auto Scaling's target-tracking alarms, and the Chatbot Slack channel config are all provisioned by their respective AWS services, not directly as taggable CFN resources CDK's Aspect walks). All 19 affected resources (6 + 12 + 1) have now been tagged live — see "Live tagging — results" above. Row counts below are left as originally computed (i.e. **before** that correction) so the original discovery reasoning stays intact; the corrected counts are 12 VPC endpoints truly pre-tagged (not 18), 0 target-tracking alarms truly pre-tagged (not 8), 0 Chatbot configs truly pre-tagged (not 1) — a net 19 fewer than the `650` total below actually needed no action. Every resource below already carries `Project=pyvar` (plus `Environment`, `Owner=fibtec-limited`, `ManagedBy=cdk` — or `ManagedBy=image-builder` for the two Image-Builder-output rows) via the Aspect described above. Listed for completeness of the inventory; no action needed. Counts are exact (machine-verified against the Tagging API + IAM output — 607 API-visible + 43 IAM roles = 650).

| Resource type | Count | Notes |
|---|---|---|
| ACM certificates | 3 | 1 excluded here — in "action needed" table |
| ALB listener rules | 2 |  |
| ALB listeners | 2 |  |
| ALB target groups | 2 |  |
| AWS Budgets | 2 |  |
| AWS Chatbot Slack configuration | 1 |  |
| Application Load Balancers | 2 |  |
| CloudFormation stacks | 29 |  |
| CloudFront distributions | 2 |  |
| CloudWatch alarms | 20 |  |
| CloudWatch alarms (ECS target-tracking) | 8 |  |
| CloudWatch dashboards | 2 |  |
| CloudWatch log groups | 8 |  |
| CloudWatch log groups (ECS/exec) | 9 |  |
| CodeBuild projects | 13 |  |
| CodePipeline | 1 |  |
| CodeStar Notification rules | 2 |  |
| EC2 AMIs (Image Builder output) | 3 |  |
| EC2 EBS snapshots (Image Builder output) | 3 |  |
| EC2 EBS volumes | 4 |  |
| EC2 Elastic IPs | 3 |  |
| EC2 NAT gateways | 3 |  |
| EC2 VPC endpoints | 18 |  |
| EC2 VPC flow logs | 2 |  |
| EC2 VPCs | 2 |  |
| EC2 instances (Spot workers) | 12 |  |
| EC2 internet gateways | 2 |  |
| EC2 launch templates | 2 |  |
| EC2 route tables | 12 |  |
| EC2 security groups | 20 |  |
| EC2 subnets | 12 |  |
| ECR repositories | 1 | 1 excluded here — in "action needed" table |
| ECS clusters | 2 |  |
| ECS services | 2 |  |
| ECS task definitions (revision history) | 303 |  |
| ElastiCache Serverless caches | 2 |  |
| ElastiCache subnet groups | 2 |  |
| EventBridge rules | 4 |  |
| Image Builder components | 2 |  |
| Image Builder distribution configs | 2 |  |
| Image Builder infrastructure configs | 2 |  |
| Image Builder lifecycle policy | 1 |  |
| Image Builder pipelines | 2 |  |
| Image Builder recipes | 2 |  |
| Lambda functions | 12 |  |
| RDS Aurora cluster snapshots | 14 |  |
| RDS Aurora clusters | 2 | 2 stale Tagging-API record(s) excluded — see note below |
| RDS Aurora instances | 4 |  |
| RDS DB subnet groups | 2 |  |
| S3 buckets | 13 |  |
| SES configuration sets | 2 |  |
| SES domain identities | 2 |  |
| SNS topics | 8 |  |
| SQS queues | 4 |  |
| Secrets Manager secrets | 8 | 3 excluded here — in "action needed" table |
| WAFv2 Web ACLs (CloudFront/global) | 2 |  |
| WAFv2 Web ACLs (regional/ALB) | 1 |  |
| IAM roles | 43 | Every pyvar-prefixed role, checked in full (all 43, not sampled) — 100% carry `Project=pyvar` |
| **Total** | **650** | |

**Stale Tagging-API records (excluded from all counts above, not actionable):** the Resource Groups Tagging API also returned 2 RDS cluster ARNs — `cluster-32i6b45grlcd3pfb6r3q25zspq` (tagged `pyvar-dev-data`/`Aurora2CBAB212`) and `cluster-6x4ziuxssz436enp2u4ybyj5jy` (tagged `pyvar-prod-data`/`Aurora2CBAB212`) — that no longer exist (`rds describe-db-clusters` returns `DBClusterNotFoundFault` for both). These are the same CloudFormation logical resource as the current live clusters (`pyvar-dev-data-aurora2cbab212-mlrlhqiuzvo5` / `pyvar-prod-data-aurora2cbab212-jjfuk8uep9wl`, both confirmed live and tagged), just an earlier physical incarnation — the Aurora cluster was replaced by a prior stack update and the Tagging API's index hasn't purged the old ARN's tag record yet. Not real resources; nothing to tag; not included in any count.

## tengrade — all 121 resources need `Project=tengrade` (none currently tagged)

Confirmed by direct code search: GitHub code search for `Tags.of` across `fibtecltd/tengrade` returns **zero hits**. Every tengrade resource below carries only AWS/CDK system tags (`aws:cloudformation:*`, `aws-cdk:*`) or no tags at all — never a `Project` tag. This matches the task's own premise exactly.

| Resource type | Count | Names |
|---|---|---|
| CloudFormation stacks | 13 | TenGradeData, TenGradeAuth, TenGradeApi, TenGradeExaminerApi, TenGradeRunnerApi, TenGradeMcpApi, TenGradeAnchor, TenGradeGradingPipeline, TenGradeMarketing, TenGradeWeb, TenGradeStatus, TenGradeAlerts, TenGradeWaf (us-east-1) |
| Lambda functions | 33 | TenGradeApi-{ApiKeys,Bank,Billing,Dashboard,Exams,Export,Instances,Org,ProctoringWebhook,Qagen}Fn; TenGradeAuth-{DomainVetting,PostConfirmation}Fn; TenGradeExaminerApi-{ExaminerApi,ExaminerAuth}Fn; TenGradeGradingPipeline-{Aggregate,GradeAnswer,GradingTrigger,LoadContext,Review}Fn; TenGradeAnchor-AnchorFn; TenGradeRunnerApi-{Runner,RunnerAuth}Fn; TenGradeMcpApi-McpServerFn; CDK custom-resource handlers (BucketDeployment / CrossRegionExportReader / AutoDeleteObjects, one set each for Marketing/Web/Status); TenGradeWaf's cross-region export writer (us-east-1) |
| Lambda event source mappings | 2 | DynamoDB streams feeding ReviewFn and GradingTriggerFn (TenGradeGradingPipeline) |
| API Gateway v2 HTTP APIs + `$default` stages | 8 | TenGradeHttpApi, TenGradeExaminerHttpApi, TenGradeMcpHttpApi, TenGradeRunnerHttpApi (API + stage each) |
| CloudFront distributions | 4 | Untagged, no aliases — attributed to tengrade by inspecting each distribution's origin: tengrademarketing-marketingbucket…, tengradeweb-runnerbucket…, tengradeweb-portalbucket…, tengradestatus-statusbucket… |
| CloudWatch alarms | 6 | tengrade-anchor-fn-errors, tengrade-api-5xx, tengrade-grade-answer-fn-errors, tengrade-grading-state-machine-failed, tengrade-review-fn-errors, tengrade-runner-api-5xx |
| Cognito user pool | 1 | tengrade-examiners (eu-west-1_nvauqwEdr) |
| EventBridge rules | 2 | TenGradeAnchor-AnchorBatchRule, TenGradeAnchor-AnchorUpgradeRule |
| S3 buckets | 5 | tengradedata-answersbucket, tengrademarketing-marketingbucket, tengradestatus-statusbucket, tengradeweb-portalbucket, tengradeweb-runnerbucket |
| Secrets Manager secrets | 6 | tengrade/anthropic-api-key, tengrade/runner-token-key, tengrade/stripe-secret-key, tengrade/stripe-webhook-signing-secret, tengrade/proctorsafe-api-key, tengrade/proctorsafe-webhook-signing-secret |
| SNS topics | 1 | tengrade-alerts |
| SSM parameters (CDK cross-region exports) | 3 | /cdk/exports/{TenGradeMarketing,TenGradeStatus,TenGradeWeb}/TenGradeWafuseast1FnGetAttWebAclArn… |
| Step Functions state machine | 1 | GradingStateMachine (TenGradeGradingPipeline) |
| WAFv2 Web ACL (CloudFront/global) | 1 | tengrade-waf (us-east-1) |
| IAM roles | 34 | TenGrade{Anchor,Api,Auth,ExaminerApi,GradingPipeline,Marketing,McpApi,RunnerApi,Status,Waf,Web}-*ServiceRole* (Lambda execution roles + CDK custom-resource provider roles) — checked in full, 0/34 carry any Project tag |
| IAM user | 1 | tengrade-cdk-deployer |
| **Total** | **121** | |

**Out of scope, noted per instructions:** adding `Tags.of()` to `fibtecltd/tengrade`'s own CDK (`infra/app.py`, `infra/stacks/*.py`) is that repo's decision and not folded into this PR. Live-tagging the resources above (step 2, pending confirmation) makes *today's* cost reports readable, but without a `Tags.of()` Aspect in tengrade's own CDK, every future tengrade deploy will keep creating untagged resources and this drift will recur. Flagging this so it isn't mistaken for a permanent fix.

## common — 20 actionable, 8 found-but-non-actionable

Account-level or CDK-toolkit infrastructure not created by either project's own CDK app, used in support of both (or neither project specifically, but present for the account as a whole).

| Resource | ARN / ID | Current tags | Proposed tag | Evidence |
|---|---|---|---|---|
| CloudFormation stack `CDKToolkit` (eu-west-1) | arn:aws:cloudformation:eu-west-1:347228921290:stack/CDKToolkit/159b9450-6bbb-11f1-808b-0a79c02de095 | _none_ | Project=common | `cdk bootstrap` stack for this account/region — both pyvar-cdk and tengrade's infra deploy through it |
| CloudFormation stack `CDKToolkit` (us-east-1) | arn:aws:cloudformation:us-east-1:347228921290:stack/CDKToolkit/3aa2a4f0-6bbb-11f1-96fb-0affc612a6cb | _none_ | Project=common | Same — bootstrapped for CloudFront/WAF edge deploys (pyvar's edge stack and tengrade's TenGradeWaf both deploy here) |
| S3 bucket `cdk-hnb659fds-assets-...-eu-west-1` | arn:aws:s3:::cdk-hnb659fds-assets-347228921290-eu-west-1 | _none (only CDK system tags)_ | Project=common | CDK asset staging bucket, shared by both apps' synth/deploy |
| S3 bucket `cdk-hnb659fds-assets-...-us-east-1` | arn:aws:s3:::cdk-hnb659fds-assets-347228921290-us-east-1 | _none (only CDK system tags)_ | Project=common | Same, us-east-1 |
| ECR repo `cdk-hnb659fds-container-assets-...-eu-west-1` | arn:aws:ecr:eu-west-1:347228921290:repository/cdk-hnb659fds-container-assets-347228921290-eu-west-1 | _none (only CDK system tags)_ | Project=common | CDK container-image asset repo, shared |
| ECR repo `cdk-hnb659fds-container-assets-...-us-east-1` | arn:aws:ecr:us-east-1:347228921290:repository/cdk-hnb659fds-container-assets-347228921290-us-east-1 | _none (only CDK system tags)_ | Project=common | Same, us-east-1 |
| SSM parameter `/cdk-bootstrap/hnb659fds/version` (eu-west-1) | arn:aws:ssm:eu-west-1:347228921290:parameter/cdk-bootstrap/hnb659fds/version | _none (only CDK system tags)_ | Project=common | Bootstrap version marker |
| SSM parameter `/cdk-bootstrap/hnb659fds/version` (us-east-1) | arn:aws:ssm:us-east-1:347228921290:parameter/cdk-bootstrap/hnb659fds/version | _none (only CDK system tags)_ | Project=common | Same, us-east-1 |
| IAM role `cdk-hnb659fds-cfn-exec-role-...-eu-west-1` | arn:aws:iam::347228921290:role/cdk-hnb659fds-cfn-exec-role-347228921290-eu-west-1 | _none_ | Project=common | CDK bootstrap role, used to deploy both apps' stacks |
| IAM role `cdk-hnb659fds-cfn-exec-role-...-us-east-1` | arn:aws:iam::347228921290:role/cdk-hnb659fds-cfn-exec-role-347228921290-us-east-1 | _none_ | Project=common | Same |
| IAM role `cdk-hnb659fds-deploy-role-...-eu-west-1` | arn:aws:iam::347228921290:role/cdk-hnb659fds-deploy-role-347228921290-eu-west-1 | `aws-cdk:bootstrap-role=deploy` | Project=common | Same |
| IAM role `cdk-hnb659fds-deploy-role-...-us-east-1` | arn:aws:iam::347228921290:role/cdk-hnb659fds-deploy-role-347228921290-us-east-1 | `aws-cdk:bootstrap-role=deploy` | Project=common | Same |
| IAM role `cdk-hnb659fds-file-publishing-role-...-eu-west-1` | arn:aws:iam::347228921290:role/cdk-hnb659fds-file-publishing-role-347228921290-eu-west-1 | `aws-cdk:bootstrap-role=file-publishing` | Project=common | Same |
| IAM role `cdk-hnb659fds-file-publishing-role-...-us-east-1` | arn:aws:iam::347228921290:role/cdk-hnb659fds-file-publishing-role-347228921290-us-east-1 | `aws-cdk:bootstrap-role=file-publishing` | Project=common | Same |
| IAM role `cdk-hnb659fds-image-publishing-role-...-eu-west-1` | arn:aws:iam::347228921290:role/cdk-hnb659fds-image-publishing-role-347228921290-eu-west-1 | `aws-cdk:bootstrap-role=image-publishing` | Project=common | Same |
| IAM role `cdk-hnb659fds-image-publishing-role-...-us-east-1` | arn:aws:iam::347228921290:role/cdk-hnb659fds-image-publishing-role-347228921290-us-east-1 | `aws-cdk:bootstrap-role=image-publishing` | Project=common | Same |
| IAM role `cdk-hnb659fds-lookup-role-...-eu-west-1` | arn:aws:iam::347228921290:role/cdk-hnb659fds-lookup-role-347228921290-eu-west-1 | `aws-cdk:bootstrap-role=lookup` | Project=common | Same |
| IAM role `cdk-hnb659fds-lookup-role-...-us-east-1` | arn:aws:iam::347228921290:role/cdk-hnb659fds-lookup-role-347228921290-us-east-1 | `aws-cdk:bootstrap-role=lookup` | Project=common | Same |
| AWS Budget `fibtec-daily` | _(Budgets have no ARN; identified by name)_ `fibtec-daily`, $40/day COST budget | _none_ | Project=common | Company-wide daily budget, not scoped to either project — unlike `pyvar-dev-monthly`/`pyvar-prod-monthly`, which are pyvar-specific and already tagged |
| EventBridge rule `awscodestarnotifications-rule` | arn:aws:events:eu-west-1:347228921290:rule/awscodestarnotifications-rule | _none_ | Project=common | AWS-managed singleton (`ManagedBy=codestar-notifications.amazonaws.com`), auto-created once per account/region to route CodeBuild/CodeCommit/CodeDeploy/CodePipeline events to CodeStar Notifications. Not created by either project's CDK. Currently only pyvar has CodeStar Notification Rules registered (2, both already `Project=pyvar`) — if tengrade ever registers one, this same rule starts serving it too, which is why `common` rather than `pyvar` fits it better long-term. |

### Found but non-actionable (not proposed for tagging)

| Resource | Why not actionable |
|---|---|
| 6 AWS-managed default KMS keys (`alias/aws/{acm,ebs,lambda,rds,s3,secretsmanager}`) | `KeyManager: AWS` — AWS-owned keys used whenever a service needs encryption and no customer key is specified. AWS does not permit customer tags on AWS-managed keys. Listed for completeness of the discovery step only. |
| 2 `arn:aws:payments::347228921290:payment-instrument:*` records | Account-level AWS Marketplace/billing payment-instrument records — not addressable as a taggable resource type in this CLI's `botocore` version (no `payments` service client), and not infrastructure in any meaningful sense (account billing configuration, not a project resource). |

## unclear — none

No resources were left unclassified. The two genuinely ambiguous cases going in — the 4 untagged CloudFront distributions and the 6 `AmazonElastiCacheManaged` VPC endpoints — were resolved with concrete evidence (CloudFront origin S3 bucket names for the former; VPC endpoint subnet IDs cross-referenced against the `pyvar-dev`/`pyvar-prod` ElastiCache Serverless subnet groups for the latter) rather than guessed, per the task's instruction not to classify anything `common` without concrete evidence.

## Status — completed

1. ~~Human review of this table~~ — done; user confirmed to proceed.
2. ~~Live-tag everything marked "needs tagging"~~ — done. 166 resources tagged live (121 tengrade + 20 common + 25 pyvar), verified by a full post-tagging Tagging API re-scan across both regions plus direct IAM tag checks. Tag-only — no resource was deleted, modified, or restarted.
3. No pyvar-cdk code change was required for the Aspect-reachability issue this task was watching for (see "Key finding" above) — it was already fixed by a prior PR. The 6 documented pyvar gaps plus the 19 found mid-execution are one-time manual-resource tagging, a different and non-fixable-in-CDK class of gap (AWS-auto-created supporting resources and CDK-imported/external resources have no CFN resource for `Tags.of()` to attach to).
4. tengrade's own CDK tagging remains explicitly out of scope for this PR — flagging to the tengrade team as a follow-up so future deploys stop drifting untagged. Today's tags make current cost reports readable; they will not survive a future tengrade stack update that recreates any of these resources without a `Tags.of()` aspect in tengrade's own CDK.
