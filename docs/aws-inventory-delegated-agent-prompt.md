# AWS resource inventory: delegated agent prompt (read-only)

**Status: draft, 2026-11-13; no run has been made.** Written after the AWS evidence run (`docs/p9-aws-evidence-2026-11-13.md`, in PR #428) found that the account is shared with other Fibtec products and that the `Project` and `Environment` tags, which the resources already carry in code, are not activated as cost-allocation tags, so Cost Explorer cannot split the bill by product or environment. This inventory maps the large fixed cost lines to products now, before the tags have data. It changes nothing in AWS; the agent needs read-only access (list, describe, get, pricing). Its report goes into the evidence document.

The prompt, as the agent should read it:

---

TASK: a read-only inventory of what the AWS account spends its fixed money on, mapped to products. Change nothing.

CONTEXT
One AWS account (main region eu-west-1; CloudFront WAF and certificates in us-east-1) hosts pyvar (prod and dev) and other Fibtec products. Cost Explorer cannot split by product because the Project and Environment tags are not activated as cost-allocation tags. Resources should already carry Project (the product name) and Environment tags set in CDK. I need to know, for each large cost line, which product owns it.

RULES
- Read-only: list, describe, get, and `pricing get-products` only. No create, modify, delete, tag, start, stop or invoke.
- Never read secret values, database contents, S3 objects, log bodies or Lambda environment variables. Names, ARNs, tags, counts and sizes only. Call no product's endpoints.
- Cost Explorer calls cost about $0.01 each: at most 30.
- If a call is denied, say so and carry on. Do not widen your access (no new roles, no policy edits).

DO
1. `ce list-cost-allocation-tags`: the status of Project, Environment, Owner, ManagedBy, CostComponent.
2. Inventory eu-west-1 and us-east-1, and check by the Resource Groups Tagging API and a few counts whether any other region holds anything: Aurora and RDS clusters and instances (engine, serverless v2 min and max ACU); ElastiCache (serverless caches and clusters); NAT gateways; VPCs; interface VPC endpoints (count per VPC and service); load balancers; ECS clusters and services (desired count, launch type); EC2 instances and Auto Scaling groups (min, max, desired); Elastic IPs and public IPv4 addresses; WAFv2 web ACLs (REGIONAL and CLOUDFRONT); CloudFront distributions; Route 53 hosted zones; CloudWatch log groups (count and stored bytes by name prefix); S3 buckets (names and tags only, no object listing). Counts only for Lambda functions, DynamoDB tables, SQS queues, Cognito pools and secrets.
3. For every resource record: product (tag Project; if missing, infer from the name prefix and mark "inferred"; else "unknown"), environment (tag Environment, else inferred) and whether it is tagged.
4. Map these October 2026 fixed lines to resources: Aurora ACU hours $314.37; ElastiCache $208.32; VPC endpoint hours $163.68; NAT hours $107.14; Fargate $55.16; ALB $37.50; WAF $36.18; CloudWatch $28.62; public IPv4 $26.06. For each line: the resources, their products, and an estimate of each product's share from resource counts and unit prices (`pricing get-products`; state the prices and the date). Reconcile the estimate to the bill line and say how far off it is. Say plainly what is shared and cannot be split by tag (for example one cluster used by several products).
5. List the untagged resources by type with the inferred product, and anything that looks orphaned (running, apparently unused). Do not touch it.

REPORT (short)
1. Tag status. 2. A table of the nine lines: line, dollars, resources, share (pyvar prod, pyvar dev, other products, unknown), the method and the error. 3. Untagged list. 4. What you could not see. 5. Everything you got wrong along the way.
Keep account ids, hostnames and secret names out of the report body; put raw output in /tmp/inv and say where. State every figure's source and any estimate as an estimate.
