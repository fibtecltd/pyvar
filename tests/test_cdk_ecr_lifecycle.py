"""tests/test_cdk_ecr_lifecycle.py — the API image repositories keep their newest 30 images.

Reasoning:
- pyvar-dev-api and pyvar-prod-api are not CDK resources (api_stack.py imports them by name), so the pipeline's image
  step sets the policy itself. Without one the prod repository held 157 images. The policy keeps the newest 30,
  tagged or not, and the Synth role needs ecr:PutLifecyclePolicy on both repositories.
- A tag that falls out of the newest 30 can no longer be pulled, so the number is pinned here: a change must be deliberate.
- The CDK code is read, not run, so aws-cdk-lib is not needed in the application test environment.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "pyvar-cdk" / "stacks" / "pipeline_stack.py"


def _text() -> str:
    if not SOURCE.exists():
        pytest.skip(f"source file not found (cannot audit): {SOURCE}")
    return SOURCE.read_text(encoding="utf-8")


def _constants() -> dict[str, object]:
    """Evaluate the two module-level constants without importing the stack (and aws-cdk-lib)."""
    tree = ast.parse(_text())
    wanted = {"_ECR_KEEP_NEWEST", "_ECR_LIFECYCLE_POLICY"}
    namespace: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in wanted for t in node.targets
        ):
            exec(
                compile(ast.Module([node], []), str(SOURCE), "exec"), {"str": str}, namespace
            )  # noqa: S102  # nosec B102
    return namespace


def test_the_policy_is_valid_json_and_keeps_the_newest_thirty() -> None:
    constants = _constants()
    assert constants["_ECR_KEEP_NEWEST"] == 30
    policy = json.loads(str(constants["_ECR_LIFECYCLE_POLICY"]))
    (rule,) = policy["rules"]
    assert rule["rulePriority"] == 1
    assert rule["selection"] == {
        "tagStatus": "any",
        "countType": "imageCountMoreThan",
        "countNumber": 30,
    }
    assert rule["action"] == {"type": "expire"}


def test_both_repositories_get_the_policy_in_the_image_step() -> None:
    text = _text()
    for repo in ("pyvar-dev-api", "pyvar-prod-api"):
        assert re.search(
            rf"aws ecr put-lifecycle-policy --repository-name {repo} --region", text
        ), f"the image step must set the lifecycle policy on {repo}"
    assert text.count("--lifecycle-policy-text '{_ECR_LIFECYCLE_POLICY}'") == 2


def test_setting_the_policy_never_blocks_a_deploy_and_runs_on_every_execution() -> None:
    """Outside the `set -e` build-or-reuse block, and each command ends in `|| echo`."""
    text = _text()
    block_end = text.index('"set +e",', text.index("def _image_build_commands"))
    after = text[block_end : text.index("# ── Prod AMI bake trigger")]
    assert after.count("aws ecr put-lifecycle-policy") == 2
    assert after.count('|| echo "WARNING: could not set the ECR lifecycle policy') == 2
    before = text[text.index("def _image_build_commands") : block_end]
    assert "put-lifecycle-policy" not in before


def test_the_synth_role_may_put_the_policy_on_both_repositories() -> None:
    text = _text()
    for repo in ("pyvar-dev-api", "pyvar-prod-api"):
        statement = re.search(
            r"actions=\[(?P<actions>[^\]]*?)\],\s*resources=\[f\"arn:aws:ecr:[^\"]*repository/"
            + repo
            + r"\"\]",
            text,
            flags=re.DOTALL,
        )
        assert statement, f"no IAM statement found for {repo}"
        assert '"ecr:PutLifecyclePolicy"' in statement.group("actions")
