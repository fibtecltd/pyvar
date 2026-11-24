# Releasing the directory plugins (`plugins-release`)

The 13 plugins listed on claude.ai/directory/manage (8 domain plugins in `plugins/<domain>`, 5
architecture plugins in `plugins/arch/<layer>`) follow the branch `plugins-release`, not `master`.
While they followed master, every merge, even billing or portal work, created a new version of all
13, started a re-scan and cancelled any publish request that was waiting for review. Now master moves
freely and the directory sees a new commit only when `plugins-release` is advanced on purpose.

## Who follows which branch

| What | Follows |
|---|---|
| The 13 directory listings (8 domain, 5 `arch`) | `plugins-release` |
| `pyvar-mcp` and `tengrade` (published through platform.claude.com) | the default branch, `master` |
| `/plugin marketplace add fibtecltd/pyvar` | the default branch, `master` |
| CodePipeline (Test, Build, Dev, Prod) | pushes to `master` only; `plugins-release` never starts a run |

`master` stays the default branch. `plugins-release` receives master only through release pull
requests (below), so its plugin files are always files that were already on master.

## When to advance it

Only when something under `plugins/` (other than `plugins/mcp/`) or under `.claude-plugin/` has
changed on master and is ready to publish. Billing, portal, API, engine, tests, scripts and docs
changes never need a release. Batch plugin changes into one release instead of several small ones:
any change that lands on `plugins-release` creates a new version of every plugin, starts a re-scan and
cancels any publish request still waiting, so each advance costs a re-scan of all 13.

Before the release, on master, run the checks from `docs/plan-plugin-marketplace-status-and-submission.md`
("Before each submission"): regenerate with `scripts/sync_skills.py` and `scripts/generate_plugins.py`,
run `claude plugin validate ./plugins/<name> --strict`, and
`pytest tests/test_plugin_directory_policy.py tests/test_skills_sync.py`. The `plugins-drift-check` job
does the regeneration check on every PR to master.

## How

1. See what the release would change:
   `git fetch origin && git diff --stat origin/plugins-release origin/master -- plugins .claude-plugin ':!plugins/mcp'`
   If it prints nothing, stop: there is nothing to release.
2. Open a pull request with base `plugins-release` and head `master`, titled `Release plugins: <what
   changed>`.
3. Merge it with **Create a merge commit**. Do not squash or rebase: both write master's commits again
   under new SHAs, so the two branches diverge and the next release PR lists every commit twice. A
   protected branch cannot take a direct fast-forward push, so a merge commit is the route.
4. Do not push to `plugins-release` any other way, never force-push it and never delete or recreate it.

Two workflows run on a release PR. `plugins-ci` listens to PRs into `plugins-release` as well as
`master` and `develop`, filtered to plugin paths. `plugins-release-changes`
(`.github/workflows/plugins-release-changes.yml`) adds a job summary that lists the plugin directories
whose files differ, so you can see where the content changed. The other workflows listen to PRs into
`master` and `develop` only; what a release carries was already checked when it merged to master.

## After the merge

The directory scans the new commit within about 6 hours. Then, on claude.ai/directory/manage, request
publishing for each listing that shows an update, as before.

Changing the branch a listing tracks cancels a waiting publish request. The branch setting of each
listing is therefore changed once, to `plugins-release`, and then left alone.

## Protection on GitHub

`plugins-release` takes changes only through pull requests. The GitHub ruleset `plugins-release`
(ID 27980975, active, no bypass) covers that branch only:

- it requires a pull request before merging, with 0 required approvals;
- it blocks force pushes and blocks deletion;
- it has no bypass for anyone, administrators included;
- "require linear history" is off because it would refuse the merge commits;
- no status check is required, so nothing stops a merge while `plugins-ci` is still running or has
  failed: look at it before you merge a release.

The ruleset `delete-forcepush` (ID 17923559) still covers `master` only.
