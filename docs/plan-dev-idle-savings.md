# D3: what dev's fixed costs can pause, shrink or lose (research, no change made)

Decision of 2026-11-16 (D3, option 4): look at scaling dev's stateful services down when idle. This is the research the
decision needs. **Nothing here has been built.** A research subagent read AWS documentation and AWS's published
price lists on 2026-11-17 (read-only, no AWS account calls); the claims marked **checked** below were re-read by
me against the same pages and files, the others are the subagent's reading. Prices are eu-west-1, 730 hours a month.
Dev costs about $403 a month of the nine fixed lines (`docs/p9-aws-evidence-2026-11-13.md`, section 8).

## The finding that matters most: the cache minimum applies to prod too

- ElastiCache Serverless bills a **minimum of 1 GB of data for Redis OSS and 100 MB for Valkey** (checked, AWS pricing
  page), at **$0.140 and $0.094 per GB-hour** in eu-west-1 (checked, AWS price list of 2026-11-16).
- October billed **$104.16 for dev and $104.16 for prod**: exactly 744 h x 1 GB x $0.14, so both caches sit on the
  minimum (`docs/p9-aws-evidence-2026-11-13.md`, section 8).
- On Valkey the same caches would cost 744 h x 0.1 GB x $0.094 = about $7 each if their data stays under 100 MB:
  **about $95 a month saved per environment, about $190 in all**, independent of how many hours dev is used.
- There is **no pause** for ElastiCache Serverless: billing continues "until the cache is deleted" (checked).
- Changing `engine` and adding `major_engine_version` on `CfnServerlessCache` is "No interruption" in
  CloudFormation (checked). The subagent also read an in-place CLI path that keeps the endpoint name, with minimal
  downtime, and warns that rollback is only possible from Valkey 7.2 to Redis OSS 7.1 (not re-read by me).
- Not known: how much data each cache holds (`BytesUsedForCache` in CloudWatch), whether the app uses anything
  Valkey lacks (the app uses redis-py 8.1.0 for the result cache, rate limits, and the Celery result backend), and
  what happens to in-flight results during the change. Measure first; try it in dev before prod.

## Aurora auto-pause (dev, 0 ACU)

- **Possible (checked, AWS Aurora user guide):** engine 16.3 or later (dev runs 16.13), `MinCapacity: 0` with
  `SecondsUntilAutoPause` (300 to 86,400 s), no downtime to change. Billing while paused is storage only.
- **What stops a pause (checked):** any open user connection; patching or upgrades in progress; an RDS Proxy;
  logical replication; a global database; any provisioned instance. Performance Insights and Enhanced Monitoring do not.
- **First connection after a pause (checked):** typically about 15 seconds, 30 seconds or longer after a day paused.
  Under a burst some sessions may fail to connect and should retry.
- **Two things in this repository keep dev awake, so the saving needs both changed together:**
  1. The API keeps database connections open: `storage/session.py` uses a pool (`pool_size=5`, `pool_pre_ping`,
     `pool_recycle=1800`, checked) and pre-ping and recycling act on checkout, so an idle connection stays open. The
     reconciler added for C5 (`storage/reconcile.py`) uses the same pool, so it keeps one open too while the API runs.
     Aurora can pause only while no API task is running, or if the pool were replaced by `NullPool`.
  2. A scheduled Lambda posts a VaR job to dev every 15 minutes (`public_data_stack.py`, checked), so dev is never
     idle while that rule is enabled; it also wakes the API if Fargate is scaled to zero.
- **Saving (the subagent's arithmetic, assuming dev is awake 8 hours a day):** about $34 to $43 a month for the writer
  (the dev reader is already removed).

## The other fixed items

| Item | Pause or zero | Dev saving a month | Notes |
| --- | --- | --- | --- |
| Interface endpoints (5 x 2 AZs, $0.011 per endpoint-hour) | no; shrink to 1 AZ | about $40 | losing the AZ loses the endpoint for the other; fine for dev. Dropping all five and relying on NAT saves about $80 but breaks `CLAUDE.md` 3.4 (no direct internet route for these services) and breaks even near 2,100 GB a month of NAT traffic (no byte count known) |
| ECS Container Insights | yes, a cluster setting | about $6 to $10 | `containerInsights` `disabled`; the bill is custom metrics at $0.30 per metric-month; dashboards would stop |
| Fargate dev API (scheduled actions to 0 and back) | yes | about $12 | 503 while off, about 2 to 3 minutes to start, no automatic wake-up; only useful together with the Lambda rule and the connection pool above |
| NAT gateway ($0.048 per hour) | no | about $32 with a NAT instance | cannot be removed (workers `git clone` from GitHub at boot, the API calls Stripe and Sentry); a NAT instance is yours to patch |
| ALB ($0.0252 per hour) | no | $0 | nothing cheaper fits this stack |

## Recommendation (unchanged from the subagent, with the prod cache added)

1. **Measure both caches' data size**, then move the **dev cache to Valkey** first (about $95 a month), and decide prod
   after dev has run on it for a while. Largest saving, one property.
2. **Endpoints to one AZ in dev** (about $40) and **Container Insights off in dev** (about $6 to $10): one change each.
3. **Aurora pause, the Fargate schedule and the 15-minute Lambda rule as one bundle** (about $46 to $55), last: three
   changes that depend on each other and on the pool, with a 15-second wait on the first request of a day.
4. **NAT instance** only if wanted; **leave the ALB**.

The recommended items together would take roughly $190 to $235 off dev's $403 (the subagent's arithmetic, with the
cache and traffic assumptions above); the prod cache change would come on top.

## Dev cache to Valkey: what AWS documents (read 2026-11-17), and what was built

**Decision (owner, 2026-11-17): yes, dev first.** Built in the pull request that carries this file: `cache_engine="valkey"` and
`cache_major_engine_version="7"` in dev's override in `pyvar-cdk/config.py`, passed to the cache in `pyvar-cdk/stacks/data_stack.py`;
the logical ID `RedisServerless` and the name `pyvar-dev` are unchanged. `cdk synth` of the whole app before and after: dev differs in
exactly two lines (`Engine` "redis" to "valkey", `MajorEngineVersion` absent to "7"), all 17 prod templates are identical.

What the AWS pages say (ElastiCache User Guide "Upgrading engine versions including cross engine upgrades" and "Version Management";
the CloudFormation `AWS::ElastiCache::ServerlessCache` page; the `ModifyServerlessCache` API and CLI references):

- CloudFormation: `Engine` and `MajorEngineVersion` both say "Update requires: No interruption"; `ServerlessCacheName` says "Replacement".
  `Engine` allows `valkey`, `redis` and `memcached`; `MajorEngineVersion` is "an integer (for example, 7, 8, or 9), not a decimal".
  The page does not say whether a Redis cache may be switched to Valkey this way.
- The API (`ModifyServerlessCache`) takes `Engine` ("the options are valkey, memcached or redis") and `MajorEngineVersion`; the User Guide
  has a section "Upgrading a Redis OSS serverless cache to Valkey with the CLI": `aws elasticache modify-serverless-cache
  --serverless-cache-name myCluster --engine valkey --major-engine-version 9`.
- "All aspects of your application, including the endpoint DNS name, will remain unchanged"; "minimal downtime" (stated in general, not
  separately for serverless); major version upgrades of serverless caches are "performed without downtime to your application".
- **Rollback: "ElastiCache only supports rolling back from Valkey 7.2 to Redis OSS 7.1."** That is why dev goes to major version 7
  and not 8 or 9; a later bump is its own change and ends the rollback path. Any user group on the cache must use engine type REDIS
  (none exists here).
- One search result (not read: the page refused the fetch) reports a bug when a serverless cache is moved Redis, Valkey, Redis,
  Valkey in a row. This change does not do a round trip, and rolling back and forward again should be avoided.

**Not verified, and what happens if it is wrong.** The pages do not state that **7** is a valid target for a serverless Redis OSS 7.1
cache (the only value they show is 9, in the CLI example, and a console parameter group named for 8), nor that CloudFormation can make
this particular change in place. If the API refuses, the dev data stack update fails and CloudFormation rolls it back to Redis; nothing
else in the stack changes in that update. If it accepts, expect the cache to be briefly unavailable ("minimal downtime"); the dev API
reads and writes the cache for the Celery result backend and rate limits, so dev may see errors for that period. Prod is untouched.

**After the dev deploy:** `aws elasticache describe-serverless-caches` should show engine `valkey` and version 7.x on the same endpoint;
dev smoke checks as usual; `BytesUsedForCache` keeps its name and dimension (`clusterId`) for Valkey (documented). Billing shows the
change from the next full day (storage minimum 0.1 GB against 1 GB). Prod follows only after dev has run cleanly, as a one-line override.

## What was not verified

Data stored in each cache; NAT, endpoint and Aurora storage volumes; the CDK release that added
`serverless_v2_auto_pause_duration` (the repository pins `aws-cdk-lib>=2.130.0`); the exact property names of
scheduled scaling in CDK; whether dev's CloudFront caches the 503 an empty ALB returns; Aurora's real resume time on
this cluster; the NAT-instance, public-IPv4 and cross-AZ pricing details the subagent gave from memory.
The subagent reported four wrong turns of its own (guessed URLs that returned only a title, a price looked up in the
wrong file, an expectation that Performance Insights blocks a pause, and a search summary about a parameter-group
conflict for Valkey that it could not resolve).
