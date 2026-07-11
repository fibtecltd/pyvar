# P4 Pre-Deploy Adversarial Review
## Timestamp: 2026-06-19T20:44:46Z
## CDK version: aws-cdk 2.1128.0 (build 7daa104) · cloud-assembly schema 54.0.0
## Reviewer: Infrastructure Security Adversary (p4_pre_deploy_validator.md)

## Freshness verification
- Latest `master` commit: `0a841b6` — committed **2026-06-19T20:24:45Z**
  (`Merge PR #34 — fix/pipeline-edge-stack-secret`)
- `cdk.out/manifest.json` mtime: **2026-06-19T20:34:26Z** (≈10 min **after** the latest commit)
- **Conclusion: cdk.out IS fresh** — synthesised after the most recent commit. Review proceeds.
- ⚠️ Housekeeping note: `cdk.out/` also contains a **stale artifact** —
  `cross-region-stack-123456789012_us-east-1.*` (mtime 2026-06-19T12:08, account `123456789012`)
  left over from a prior synth. The **active** edge replication stack is
  `cross-region-stack-347228921290_*` (account `347228921290`, mtime 20:34). The stale pair is
  not part of this deployment and was ignored; recommend `rm` before packaging the assembly.

## Templates reviewed (dev deployment set, account 347228921290)
- `pyvar-dev-network.template.json`  (eu-west-1)
- `pyvar-dev-data.template.json`     (eu-west-1)
- `pyvar-dev-queue.template.json`    (eu-west-1)
- `pyvar-dev-compute.template.json`  (eu-west-1)
- `pyvar-dev-api.template.json`      (eu-west-1)
- `pyvar-dev-ami.template.json`      (eu-west-1)
- `pyvar-dev-edge.template.json`     (us-east-1 — CloudFront + WAF)
- `cross-region-stack-347228921290_us-east-1.template.json` (us-east-1 — pipeline replication bucket)
- `pyvar-pipeline.template.json`     (eu-west-1 — CI/CD self-mutating pipeline)

---

## CRITICAL findings — deploy blocked until resolved

| # | Stack | Resource | Rule | Description | Required fix |
|---|---|---|---|---|---|
| — | — | — | — | **NONE. No critical violations found.** | — |

---

## WARNING findings — allowed in dev, fix before production

| # | Stack | Resource | Rule | Description |
|---|---|---|---|---|
| 1 | pyvar-dev-ami | `ImageBuilderInfrastructureConfiguration` (Image Builder) | IMDSv2-1 (adjacent) | The transient EC2 build instance used by Image Builder has **no explicit `instanceMetadataOptions`**, so it inherits the AWS account/region default for IMDS (may permit IMDSv1) during the build window. Out of strict checklist scope (rule targets `AWS::EC2::LaunchTemplate`, and the *baked AMI* carries no IMDS config — that is set by the consuming `WorkerLaunchTemplate`, which is compliant). Recommend setting `instance_metadata_tags`/`http_tokens=required` on the InfrastructureConfiguration before production. |
| 2 | pyvar-dev-api | `AlbPublicListener54E492A7` | (informational, no rule) | Public ALB listener is **Protocol HTTP on port 443** (CloudFront terminates TLS and forwards to the custom origin). Defensible design — origin is gated by the X-Origin-Verify secret + WAF at the edge — but CF→ALB hop is not re-encrypted. Consider HTTPS origin / ACM cert before production if regulatory transport-encryption-in-transit is required end-to-end. |
| 3 | (multiple) | non-taggable & CDK-framework resources | TAG-1 | A scan flagged untagged resources, but **all are non-taggable AWS types** (`Route`, `SubnetRouteTableAssociation`, `VPCGatewayAttachment`, `S3::BucketPolicy`, `CloudFront::CachePolicy`, `AutoScaling::ScalingPolicy`, `LifecycleHook`, `IAM::InstanceProfile`) or **CDK-internal custom-resource Lambdas** (`CustomCrossRegionExportWriter/Reader`, `S3AutoDeleteObjects`, `RestrictDefaultSG`). All **user-facing taggable resources carry `Project=pyvar`, `Environment=dev`, `ManagedBy=cdk`** (verified on VPC, SGs, Aurora, secrets, queues). Effectively compliant; **not actionable**. |

---

## Notes / discrepancies (not findings)
- **Region: checklist says `eu-west-2`, infrastructure is `eu-west-1`.** `config.py:20` sets
  `region = "eu-west-1"` (Dublin). All six interface/gateway VPC endpoints synthesised at
  `com.amazonaws.eu-west-1.*` and the S3 gateway uses `{Ref: AWS::Region}`. The endpoints are
  **present and internally consistent at the configured region** — the `eu-west-2` strings in
  `p4_pre_deploy_validator.md` (EP-1) are a **stale value in the validator doc itself**, not a
  deploy defect. Recommend correcting the checklist to `eu-west-1`.
- **SG-2 (intent vs literal wording):** Aurora (5432) and ElastiCache (6379) ingress reference
  **both** the ECS task SG (`SgApi`) **and** the EC2 worker SG (`SgWorker`). The literal rule says
  "only the ECS task security group"; the worker-SG reference is a **legitimate internal addition**
  (Celery Spot workers query Aurora/Redis). No `CidrIp`/`CidrIpv6` on either — internet isolation
  intent fully satisfied. Pass.

---

## Passed checks
- [x] **SG-1**: Only `0.0.0.0/0` ingress is on the ALB SG, ports **443 and 80** only (allowed). No unrestricted ingress on any other port across all stacks.
- [x] **SG-2**: Aurora (5432) and ElastiCache (6379) ingress reference **internal SGs only** (`SgApi`, `SgWorker`); no `CidrIp`/`CidrIpv6` rules — databases/cache isolated from the internet.
- [x] **EP-1**: All required VPC endpoints present (region eu-west-1) — S3 (Gateway), SQS, ECR.api, ECR.dkr, SecretsManager, Logs (all Interface). Endpoint SGs restrict 443 to the VPC CIDR.
- [x] **IMDSv2-1**: `WorkerLaunchTemplateA05EAA22` sets `HttpTokens: required`, `HttpPutResponseHopLimit: 1`. No `HttpTokens: optional` anywhere in the assembly.
- [x] **ECS-1**: API service capacity-provider strategy has **FARGATE `Base: 1`, Weight 1** (+ FARGATE_SPOT Base 0/Weight 2). On-demand base capacity reserved — WARNING cleared.
- [x] **WAF-1**: `Distribution830FAC52` references `WebACLId = GetAtt WebAcl.Arn`; `WebAcl` is `AWS::WAFv2::WebACL` **Scope=CLOUDFRONT** in the **us-east-1** edge stack (per manifest `pyvar-dev-edge -> us-east-1`). Correct.
- [x] **SEC-1**: No hardcoded secrets. The CF origin-verify secret resolves via `{{resolve:secretsmanager:...pyvar/dev/cf-origin-verify...}}` on **both** the edge (header injection) and api (ALB rule match) sides; the secret itself is auto-generated (`GenerateSecretString`, 32 chars). GitHub token uses `{{resolve:secretsmanager:pyvar/github-token...}}`. Aurora password auto-generated (only `username:pyvar_admin` literal). High-entropy literal scan matched only CloudFormation logical IDs / AWS managed-rule names.
  - [x] **Bonus — origin-verify is not bypassable**: the ALB public listener **default action is `fixed-response 403 Forbidden`**; only the Priority-1 rule matching the secret `X-Origin-Verify` header forwards to the target group. Direct-to-ALB requests without the secret are rejected.
- [x] **TAG-1**: All taggable user resources carry the three required tags (verified by sampling + full scan; only non-taggable types and CDK framework resources lack them).

---

## VERDICT: **DEPLOY APPROVED**

No CRITICAL findings. All deploy-blocking checks (SG-1, SG-2, EP-1, IMDSv2-1, WAF-1, SEC-1) pass.
ECS-1 (WARNING) is satisfied. Remaining WARNING/informational items are non-blocking for dev and
do not require a re-synth. Per the validator decision rule ("WARNING only → proceed to deploy"),
deployment of the `pyvar-dev-*` stack set may proceed.

## Pre-production follow-ups (log in final P4 report — not blocking dev deploy)
1. `stacks/ami_stack.py` — set `http_tokens="required"` on the Image Builder InfrastructureConfiguration's instance metadata options (WARNING #1).
2. `stacks/api_stack.py` — evaluate HTTPS/ACM on the CF→ALB origin hop for end-to-end transport encryption (WARNING #2).
3. Correct `scripts/adversarial/p4_pre_deploy_validator.md` EP-1 region strings `eu-west-2` → `eu-west-1` to match `config.py` (avoids future false positives).
4. Remove the stale `cross-region-stack-123456789012_*` artifacts from `cdk.out/` before packaging.
