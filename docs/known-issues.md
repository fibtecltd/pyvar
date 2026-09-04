# Known issues and workarounds — infra/tooling

Entries here follow the same format as `CLAUDE.md` §11 ("Known issues and
workarounds"), but live under `docs/` instead of in `CLAUDE.md` itself
deliberately: `docs/**` is one of the 8 top-level directories excluded from
the CodePipeline Git push-filter trigger (see
`pyvar-cdk/stacks/pipeline_stack.py`'s `_TRIGGER_EXCLUDED_PATHS`), while
`CLAUDE.md` is a root-level file the trigger has no room left to exclude.
An edit to this file won't start an unnecessary pipeline execution the way
an edit to `CLAUDE.md` would.

---

```
ISSUE: pipeline_stack.py's Git push-filter trigger (_TRIGGER_EXCLUDED_PATHS)
       only excludes 8 top-level DIRECTORIES from starting a pipeline
       execution -- AWS::CodePipeline::Pipeline hard-caps
       filePaths.{includes,excludes} at 8 entries, and that list is exactly
       full today (.claude, .claude-plugin, .github, docs, ingestion,
       pyvar-client, scripts, tests). It has no room for individual
       top-level FILES like .pre-commit-config.yaml, pyproject.toml,
       README.md, or CHANGELOG.md -- a push touching only one of those still
       starts a full pipeline execution (Test/Build/Dev-deploy) even though
       nothing portal-relevant changed. CLAUDE.md itself is one such file --
       see this file's own header note above for why these entries live
       here instead.
FIX:   None applied -- accepted as a low-frequency cost. Confirmed 2026-09-04
       via PR #325 (docs/publications/** + a one-line
       .pre-commit-config.yaml edit): the docs/** files were correctly
       excluded, but the .pre-commit-config.yaml change alone was enough to
       start an execution. Impact is bounded, not dangerous: Dev's steps
       have skip-gates that no-op when nothing portal-relevant changed
       (_skip_gate_commands), and Prod is behind
       `require_prod_approval: bool = True` in pyvar-cdk/config.py -- a
       human still has to approve Prod, this gap alone can't reach it
       unattended. A possible fix if this becomes frequent enough to
       matter: .claude and .claude-plugin could merge into one glob entry
       (".claude*/**") to free a slot for individual files -- NOT done
       here, since it would need verifying against AWS's actual
       CodeConnections push-filter glob semantics first (unconfirmed in
       this session, no live AWS access to test it), and getting a
       production pipeline gate wrong is worse than the cost it would save.
```
