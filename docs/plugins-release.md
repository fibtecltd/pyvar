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
the directory may treat any new commit on the branch as a new version of every listing (that is what
happened on master), so each advance costs a re-scan of all 13.

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

The release PR starts none of the existing workflows (they listen to PRs into `master` and `develop`);
what it carries was already checked when it merged to master. If the workflow
`.github/workflows/plugins-release-changes.yml` is present, it adds a job summary to the PR that lists
the plugin directories whose files differ, so you can see where the content changed.

## After the merge

The directory scans the new commit within about 6 hours. Then, on claude.ai/directory/manage, request
publishing for each listing that shows an update, as before.

Changing the branch a listing tracks cancels a waiting publish request. The branch setting of each
listing is therefore changed once, to `plugins-release`, and then left alone.

## Protection on GitHub

`plugins-release` is meant to take changes only through pull requests. Settings (a branch protection
rule or a ruleset targeting `plugins-release`):

- require a pull request before merging, with 0 required approvals unless a second reviewer exists;
- block force pushes and block deletion;
- no bypass for anyone, administrators included;
- leave "require linear history" off (it would refuse merge commits) and require no status checks
  (no existing workflow runs on a PR into this branch, so a required check would block every release).
