# P5 Housekeeping Report
## Date: 2026-06-29
## Account: 347228921290 · Region: eu-west-1 / us-east-1
## Branch: chore/p5-housekeeping

---

## Scope

Three housekeeping items from the P4 adversarial post-deploy review (§6, item 4):

1. Remove stale `cross-region-stack-123456789012_*` artifacts from `cdk.out/`
2. Prune stale `ApiTaskDefapiLogGroup*` CloudWatch log groups (3 groups) in eu-west-1
3. Prune retained ECR repo `pyvar-dev-api` if safe to do so

---

## Findings and actions

### 1. cdk.out cross-region-stack artifacts

**Finding:** `pyvar-cdk/cdk.out/` is listed in `.gitignore` and has never been committed
to git. No `cross-region-stack-*` artifacts exist in version control.

**Action:** None required. The stale artifacts mentioned in P4 were local ephemeral
output from operator `cdk synth` runs and were not persisted. Running `cdk synth` clean
on any branch produces a fresh `cdk.out/` with no stale entries.

**Status:** ✅ Resolved (not applicable)

---

### 2. Stale ApiTaskDefapiLogGroup* CloudWatch log groups

**Finding:** Live account query returns exactly **1** `ApiTaskDefapiLogGroup*` group:

| Group | Retention | Stored bytes | Status |
|---|---|---|---|
| `pyvar-dev-api-ApiTaskDefapiLogGroup9FDF1262-x7VdN1LfDVHy` | 30 days | 585 B | **LIVE** (active container log stream) |

The two additional stale groups referenced in the P4 audit were already cleaned up
during the stack delete/recreate cycles in P4 — they accumulated during failed first
deploys and were removed when those stack instances were deleted. Only the live group
from the current `pyvar-dev-api` CREATE_COMPLETE stack remains.

**Action:** No deletion performed — the sole surviving group is the active log stream
for the running ECS task. Deleting it would destroy container logs for the live service.

**Status:** ✅ Already clean (stale groups removed during P4 stack lifecycle)

---

### 3. Retained ECR repo pyvar-dev-api

**Finding:**

| Repo | Image | Tag | Referenced by |
|---|---|---|---|
| `pyvar-dev-api` | `sha256:27e716b2b88c...` | `latest` | Running ECS task (`pyvar-dev` cluster) |
| `pyvar-dev-api` | `sha256:751b1c14bcc4...` | *(untagged)* | Manifest list for `latest` (platform layer) |
| `pyvar-dev-api` | `sha256:ce42d213258d...` | *(untagged)* | Manifest list for `latest` (platform layer) |

The repo is currently referenced (not CDK-owned) via `ecr.Repository.from_repository_name`
in `api_stack.py`. It holds the live image pulled by the running task.

**Verdict: NOT SAFE TO DELETE** — deleting the repo would terminate the running ECS
service. It must be retained until a new image lifecycle or repo replacement is
explicitly planned.

**Action on untagged images:** Of the 5 untagged images found:
- 3 true orphans (no manifest reference) were **deleted** via `ecr batch-delete-image`:
  - `sha256:f8ca170153e1...` — deleted ✅
  - `sha256:8161ee33dfc7...` — deleted ✅
  - `sha256:00ff8cc83f20...` — deleted ✅
- 2 retained — `ImageReferencedByManifestList` (platform-specific layers for `latest` manifest):
  - `sha256:751b1c14bcc4...` — retained (manifest list child)
  - `sha256:ce42d213258d...` — retained (manifest list child)

**Status:** ✅ Partial (3 orphan images pruned; repo + 2 manifest-list layers retained as required)

---

## Summary

| Item | Expected | Found | Action |
|---|---|---|---|
| cdk.out cross-region artifacts | Remove from git | Gitignored — never committed | None |
| Stale ApiTaskDefapiLogGroup* (×3) | Delete 3 stale groups | 1 live group only; 2 stale already gone | None |
| Retained ECR repo | Confirm + delete if safe | Live — holds `latest` pulled by running task | Retained |
| Untagged ECR orphan images (×3) | (found during audit) | True orphans from P4 failed pushes | **Deleted** |
| Manifest-list ECR layers (×2) | (found during audit) | Referenced by `latest` manifest | Retained |

All P4 carry-forward housekeeping items are resolved. The account is clean.
