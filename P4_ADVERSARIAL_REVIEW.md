# P4 Pre-Deploy Adversarial Review
## Timestamp: 2026-06-17T09:07:16Z
## CDK CLI version: 2.1127.0 (build 425ccb0)
## aws-cdk-lib version: 2.260.0 (requirements.txt floor: >=2.130.0)
## AWS account verified: 347228921290 (eu-west-2 primary, us-east-1 edge)
## Templates reviewed (cdk.out/, env=dev):
- pyvar-dev-network.template.json
- pyvar-dev-data.template.json
- pyvar-dev-queue.template.json
- pyvar-dev-compute.template.json
- pyvar-dev-api.template.json
- pyvar-dev-edge.template.json  (us-east-1)
- pyvar-dev-ami.template.json
- pyvar-pipeline.template.json + cross-region-stack (us-east-1)

> **Read this first.** The security checklist (SG/EP/IMDSv2/ECS/WAF/SEC/TAG)
> **passes** on the synthesized templates. **However**, the CDK app **as committed
> did not synthesize at all** — `cdk synth`/`cdk diff` failed with nine separate
> defects. To produce reviewable templates I had to apply fixes (listed in
> §"Synthesizability blockers"). Those fixes are **uncommitted working-tree
> changes** and have **not been human-reviewed**. The final VERDICT therefore
> remains **DEPLOY BLOCKED** pending your review of those changes and account
> bootstrap. Details below.

---

## CRITICAL findings — deploy blocked until resolved

These are not from the security checklist (that passed). They are
**synthesizability defects**: the committed IaC could not be turned into a
CloudFormation template, which means it has never been validated and cannot be
deployed. Each was fixed in the working tree to allow the review to proceed.

| # | Stack / file | Location | Defect | Fix applied (working tree, UNCOMMITTED) |
|---|---|---|---|---|
| 1 | pyvar-cdk (env) | `pyvar-cdk/constructs/` | Empty local `constructs/__init__.py` (committed) shadows the PyPI `constructs` package when `python3 app.py` runs from `pyvar-cdk/`, so `from constructs import Construct` resolves to an empty module → `ModuleNotFoundError: constructs._jsii`. Breaks **all** synth/diff/deploy. | Moved dir aside to `_local_constructs_shadow_BAK/` (git shows it as a deletion). Needs a permanent decision — see §Remaining actions. |
| 2 | pipeline_stack.py | line 48 | `sm.SecretValue.secrets_manager(...)` — `SecretValue` is on the CDK **core** module, never on `aws_secretsmanager`. `AttributeError`. Latent bug; stack had never been synthed. | `cdk.SecretValue.secrets_manager(...)` |
| 3 | pipeline_stack.py | line 55 | `pipelines.GitHubTrigger.WEBHOOK` — `GitHubTrigger` lives in `aws_codepipeline_actions`, not `pipelines`. `AttributeError`. | Added `from aws_cdk import aws_codepipeline_actions as cpa`; use `cpa.GitHubTrigger.WEBHOOK` |
| 4 | compute_stack.py | ~line 182 | `AutoScalingGroup(warm_pool=...)` — not a valid constructor kwarg; warm pools attach via `asg.add_warm_pool()`. `TypeError`. | Removed kwarg; added `self.asg.add_warm_pool(...)` after construction, guarded `if cfg.env_name == "prod"` (behaviorally identical — dev never created one). |
| 5 | compute_stack.py | ~line 165 | `MixedInstancesPolicy(launch_template=LaunchTemplateOverrides(...))` — `launch_template` must be an `ILaunchTemplate`, not a `LaunchTemplateOverrides`. jsii `SerializationError`. | Pass the `ec2.LaunchTemplate` directly as `launch_template=launch_template`. |
| 6 | compute_stack.py | ~line 224 | `scale_on_metric` scaling steps were non-contiguous (`1–5`, `6–20`, `21–50`), producing **four** "no-change" gaps; CDK permits at most one. `RuntimeError: MostNoChangeInterval`. | Made band boundaries contiguous (`0–5`, `5–20`, `20–50`, `50+`) so only the scale-to-zero band is a no-change interval. Capacity mapping preserved. |
| 7 | api_stack.py | line 211 | `target_group.enable_stickiness_for_origin_header_v2(...)` — method does not exist (hallucinated API). `AttributeError`. | `target_group.enable_cookie_stickiness(Duration.hours(1))` (the real 1-hour session-stickiness API). |
| 8 | api_stack.py | ~line 168 | `network → api` **DependencyCycle**: the ECS pattern auto-creates its own ALB security group; attaching the network-owned `sgs.api` made CDK write an ingress rule onto a network-stack SG referencing the api-stack ALB SG, while `api → data → network` already existed. Synth aborts. (Source comment claimed "we attach sgs.alb manually" but never did.) | Build the ALB explicitly with `security_group=sgs.alb` (network-owned) and pass `load_balancer=alb` to the pattern, so every SG-to-SG rule stays inside the network stack. Removed `load_balancer_name`/`public_load_balancer` (illegal alongside a provided LB). |
| 9 | pyvar-cdk (env) | requirements | `aws-cdk-lib` / `constructs` / awscli were not installed in the environment. | `pip install -r pyvar-cdk/requirements.txt` (installed aws-cdk-lib 2.260.0). |

**Interpretation:** the pipeline and compute/api stacks contained multiple
errors that only surface at synth time (wrong module paths, an invalid kwarg, a
hallucinated method, a structural SG cycle). This is consistent with IaC that was
authored but **never run through `cdk synth`**. None of these would have been
caught by deploy alone — they abort before any template exists.

---

## Security checklist — result on the FIXED, synthesized templates

| Rule | Result | Evidence |
|---|---|---|
| **SG-1** No unrestricted ingress on non-80/443 | ✅ PASS | Only `SgAlb` has `0.0.0.0/0`, and only on tcp/443 and tcp/80. No other CidrIp/CidrIpv6 ingress anywhere. |
| **SG-2** DB & cache isolated from internet | ✅ PASS | `SgAurora` ingress only from `SgApi`/`SgWorker` on 5432; `SgCache` only from `SgApi`/`SgWorker` on 6379. No CidrIp on either. Aurora instances `PubliclyAccessible: false`. |
| **EP-1** Required VPC endpoints | ✅ PASS | Gateway: S3. Interface: `…eu-west-2.sqs`, `.ecr.api`, `.ecr.dkr`, `.secretsmanager`, `.logs`. All present in network stack. |
| **IMDSv2-1** IMDSv2 enforced | ⚠️ WARNING | `WorkerLaunchTemplate` has `HttpTokens: required` (the SSRF-critical setting — satisfied). But `HttpPutResponseHopLimit: 1` is **not explicit** (CDK's `require_imdsv2=True` only emits `HttpTokens`; EC2 defaults the hop limit to 1). Recommend setting it explicitly. |
| **ECS-1** FARGATE base capacity | ✅ PASS | API service strategy: `FARGATE_SPOT` base 0 / weight 2, **`FARGATE` base 1** / weight 1. On-demand base ≥1 guaranteed (also satisfies CLAUDE.md §3.4 HA rule). |
| **WAF-1** CloudFront has WAF in us-east-1 | ✅ PASS | `Distribution.WebACLId = GetAtt WebAcl.Arn`; `WebAcl` scope `CLOUDFRONT`; edge stack environment `aws://347228921290/us-east-1`. |
| **SEC-1** No hardcoded secrets | ✅ PASS | No literal secret values. Aurora master password resolves via `{{resolve:secretsmanager:…:password::}}`; the Aurora secret is a `GenerateSecretString` (only a `{"username":"pyvar_admin"}` template is literal). JWT/DB injected via `ecs.Secret.from_secrets_manager`. |
| **TAG-1** Required tags | ✅ PASS | Every taggable resource carries `Project`, `Environment`, `ManagedBy` (and `Owner`). Counts: network 35/35, api 9/9, data 9/9, queue 5/5, compute 4/4, edge 3/3, ami 1/1. |

### Step 3 review items (cdk diff)
1. **Downtime risk:** none — all stacks are new (first deployment; no existing
   stacks in the account). Expected for an initial deploy.
2. **Permissive SG rules:** none beyond ALB 80/443 (see SG-1).
3. **Missing VPC endpoints:** none (see EP-1).
4. **IMDSv2:** tokens required; hop limit not explicit (see IMDSv2-1).

---

## WARNING findings — allowed in dev, fix before production

| # | Stack | Source | Description |
|---|---|---|---|
| W1 | compute | LaunchTemplate | IMDSv2 `HttpPutResponseHopLimit` not set explicitly (relies on EC2 default of 1). Set it to `1` in the launch template for defense-in-depth. |
| W2 | compute | `scale_on_metric` | `cooldown=` is ignored on step-scaling policies (`'Cooldown' is valid only if the policy type is SimpleScaling`). The `cooldown`/`estimated_instance_warmup` intent is silently dropped — confirm scaling cadence is still acceptable or move to target tracking. |
| W3 | compute | WorkerAsg | `desiredCapacity` is set, so every deploy resets ASG size (CDK aws-autoscaling:desiredCapacitySet). Intentional here (desired=0, SQS scaling takes over) but worth acknowledging. |
| W4 | api | ECS Service | `minHealthyPercent` not configured → defaults to 50%; running task count can drop below desired during deploys. Set explicitly before prod. |
| W5 | data | Aurora | Performance Insights enabled at cluster level but disabled per-instance (writer/reader); CDK warns it will be force-enabled. Cosmetic. |
| W6 | pipeline | CodePipeline | V1 pipeline type implicitly selected; set `PipelineType.V2` for current best practice. |
| W7 | pipeline (Dev/Prod stages) | cross-stack refs | Default "strong" cross-stack reference strength; consider the `@aws-cdk/core:defaultCrossStackReferences` flag guidance before prod. |

---

## Passed checks (summary)
- [x] SG-1: non-80/443 ingress restricted
- [x] SG-2: Aurora & ElastiCache reachable only from API/worker SGs
- [x] EP-1: S3 + SQS + ECR(api/dkr) + Secrets Manager + Logs endpoints present
- [x] ECS-1: FARGATE on-demand base = 1
- [x] WAF-1: CloudFront WebACL (CLOUDFRONT scope) in us-east-1
- [x] SEC-1: no hardcoded secrets; Secrets Manager resolution used throughout
- [x] TAG-1: required tags on all taggable resources
- [~] IMDSv2-1: tokens required (PASS) / hop limit implicit (WARNING)

---

## VERDICT: DEPLOY BLOCKED

Rationale (two layers):
1. **Security axis — PASS.** On the synthesized templates there are **0 CRITICAL
   security-checklist findings** and 7 warnings (none deploy-blocking on the
   checklist's own decision rule).
2. **Synthesizability / change-review axis — BLOCK.** The committed code could not
   synthesize; nine defects (one environment, eight code/structure) had to be
   fixed in the working tree to produce any template. Those fixes are **not
   committed and not human-reviewed**, and several change real infrastructure
   behavior (ALB SG ownership, worker scaling bands, warm-pool wiring). Deploying
   from the current committed tree is impossible; deploying from my uncommitted
   tree without your review is exactly what this gate exists to prevent.

Per the runbook, deploy proceeds only at **DEPLOY APPROVED**. Holding here.

## To reach DEPLOY APPROVED — minimum actions before re-review
1. **Review the 9 fixes** in the working tree (`git diff pyvar-cdk/stacks/` plus the
   `constructs/` move) and decide each is acceptable. Pay special attention to:
   - api_stack ALB now uses the network `sgs.alb` (defect #8) — confirms intended SG topology.
   - compute_stack scaling bands made contiguous (defect #6) — confirm capacity map.
2. **Decide the `constructs/` directory's fate** (defect #1): it is empty and
   shadows a hard dependency. Recommended: delete it from the repo (it serves no
   purpose), or rename to e.g. `pyvar_constructs/` if custom constructs are planned.
   Currently moved to `pyvar-cdk/_local_constructs_shadow_BAK/`.
3. **Commit** the reviewed fixes on an `infra/*` branch (CLAUDE.md §8 requires
   `cdk diff` output in the PR for infra changes — captured above).
4. **(Optional, recommended) address** IMDSv2 hop limit (W1) and the step-scaling
   cooldown (W2) before prod.
5. **Bootstrap the account** (`cdk bootstrap` for eu-west-2 and us-east-1) — not yet
   done; the lookup role does not exist, so deploy/Step 4 cannot run regardless.
6. Re-run `cdk synth --context env=dev --quiet` and re-review (this file).

---

### Environment notes
- Node v20.20.2 is EOL (jsii warns); non-blocking. `JSII_SILENCE_WARNING_DEPRECATED_NODE_VERSION=1` used.
- `cdk diff` reported all dev stacks as new (no existing stacks; account not bootstrapped).
- Working-tree artifacts created by this review: `cdk.out/`, `cdk.context.json`,
  `_local_constructs_shadow_BAK/` (the moved shadow dir).
