"""
tests/test_var_task.py — Unit tests for the var_jobs completion audit write
(issue #118, Celery-side half of the write path — see api/routes/var.py for
the submission-side INSERT) and the large-result S3 offload (#130).

Reasoning:
- _write_terminal_audit is exercised directly against a fake sync Session
  (tasks/var_task.py uses storage/session.py's get_sync_sessionmaker, not the
  async one FastAPI routes use — see that module's docstring for why). No
  real Postgres, per the project rule of never hitting a real backing service
  in tests.
- compute_var_task's control flow is exercised via the raw undecorated
  function (type(compute_var_task).run), with a MagicMock `self` standing in
  for the Celery task context. This sidesteps needing a real broker/worker
  just to control self.request.retries / self.max_retries, and lets the
  retry-vs-terminal branch be asserted directly: a mid-retry attempt must
  NOT write a terminal audit status, only the final success/failure does —
  the guarantee that keeps Celery retries (same task_id, up to max_retries)
  from producing duplicate or flapping audit rows.
- write_result_to_s3 (storage/s3.py) is mocked at its tasks.var_task import
  site — never a real S3/MinIO call, same never-hit-a-real-backing-service
  rule.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import Retry

from config import get_settings
from tasks.var_task import _write_terminal_audit, compute_var_task

cfg = get_settings()

# ── Fakes ──────────────────────────────────────────────────────────────────────


class FakeResult:
    """Stand-in for the CursorResult returned by Session.execute(update(...))."""

    def __init__(self, rowcount: int):
        self.rowcount = rowcount


class FakeSyncSession:
    """Enough of a sync Session's interface for _write_terminal_audit."""

    def __init__(self, update_rowcount: int = 1):
        self._update_rowcount = update_rowcount
        self.added: list = []
        self.executed: list = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, stmt):
        self.executed.append(stmt)
        return FakeResult(self._update_rowcount)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True


def patch_sync_sessionmaker(fake_session: FakeSyncSession):
    return patch("tasks.var_task.get_sync_sessionmaker", return_value=lambda: fake_session)


def raw_task_run(mock_self, **kwargs):
    """Call compute_var_task's undecorated function body with a fake `self`.

    compute_var_task is a celery.local.PromiseProxy; .run is bound to the real
    Task instance, so .run.__func__ is the only way to get the plain function
    back and substitute our own `self` instead of the real task instance.
    """
    return compute_var_task.run.__func__(mock_self, **kwargs)


def make_mock_self(retries: int = 0, max_retries: int = 2, task_id: str = "task-x") -> MagicMock:
    mock_self = MagicMock()
    mock_self.request.id = task_id
    mock_self.request.retries = retries
    mock_self.max_retries = max_retries
    mock_self.name = "pyvar.tasks.compute_var"
    return mock_self


MOCK_RESULT = {
    "var_pct": 0.028,
    "var_abs": 28_000.0,
    "cvar_pct": 0.035,
    "cvar_abs": 35_000.0,
    "loss_dist": [0.0],
    "mu": 0.0003,
    "sigma": 0.012,
    "n_simulations": 10_000,
    "confidence_level": 0.99,
    "horizon_days": 1,
}

# n_simulations sits exactly at cfg.s3_result_offload_threshold — MOCK_RESULT
# above therefore stays inline (the offload check is strictly-greater-than;
# see tasks/var_task.py), and LARGE_MOCK_RESULT below is deliberately one
# above it to exercise the S3 offload path (#130).
LARGE_MOCK_RESULT = {**MOCK_RESULT, "n_simulations": cfg.s3_result_offload_threshold + 1}

PAYLOAD = {"returns": [0.001] * 30, "portfolio_value": 1_000_000.0, "n_simulations": 1000}


# ── _write_terminal_audit ────────────────────────────────────────────────────


def test_write_terminal_audit_success_updates_existing_row():
    fake_session = FakeSyncSession(update_rowcount=1)
    with patch_sync_sessionmaker(fake_session):
        _write_terminal_audit("task-1", "success", duration_ms=1234, result=MOCK_RESULT)

    assert fake_session.committed is True
    assert len(fake_session.executed) == 1
    assert fake_session.added == []  # UPDATE matched a row — no fallback INSERT


def test_write_terminal_audit_missing_row_falls_back_to_insert():
    """If no submission row exists (should not happen on the normal path),
    the completion write still lands rather than being silently lost."""
    fake_session = FakeSyncSession(update_rowcount=0)
    with patch_sync_sessionmaker(fake_session):
        _write_terminal_audit("task-2", "failure", duration_ms=500, error_message="boom")

    assert fake_session.committed is True
    assert len(fake_session.added) == 1
    assert fake_session.added[0].task_id == "task-2"
    assert fake_session.added[0].user_id == "unknown"


def test_write_terminal_audit_db_error_is_swallowed():
    """A DB outage on the completion write must never raise into the caller —
    the Celery task itself must not fail over a pure persistence problem."""

    class ExplodingSession(FakeSyncSession):
        def commit(self):
            raise RuntimeError("simulated DB outage")

    fake_session = ExplodingSession()
    with patch_sync_sessionmaker(fake_session):
        _write_terminal_audit("task-3", "success", duration_ms=1, result=MOCK_RESULT)
    # No exception propagated — that's the assertion.


# ── compute_var_task: retry vs terminal ─────────────────────────────────────


def test_compute_var_task_success_writes_terminal_audit_once():
    fake_session = FakeSyncSession()
    mock_self = make_mock_self()

    with (
        patch_sync_sessionmaker(fake_session),
        patch("engine.montecarlo.run_monte_carlo_var", return_value=MOCK_RESULT),
        patch("tasks.var_task._emit_job_metric"),
    ):
        result = raw_task_run(mock_self, payload=PAYLOAD)

    assert result == MOCK_RESULT
    assert len(fake_session.executed) == 1
    mock_self.retry.assert_not_called()


def test_compute_var_task_mid_retry_does_not_write_terminal_audit():
    """A transient failure that still has retries left must raise Retry and
    must NOT touch the var_jobs row — only the final terminal outcome does."""
    fake_session = FakeSyncSession()
    mock_self = make_mock_self(retries=0, max_retries=2)
    mock_self.retry.side_effect = Retry(exc=ValueError("transient"))

    with (
        patch_sync_sessionmaker(fake_session),
        patch("engine.montecarlo.run_monte_carlo_var", side_effect=ValueError("transient")),
        patch("tasks.var_task._emit_job_metric"),
    ):
        with pytest.raises(Retry):
            raw_task_run(mock_self, payload=PAYLOAD)

    assert fake_session.executed == []
    assert fake_session.added == []
    mock_self.retry.assert_called_once()


def test_compute_var_task_terminal_failure_writes_audit():
    """Once retries are exhausted, the terminal failure IS written and the
    original exception (not a Retry) propagates."""
    fake_session = FakeSyncSession()
    mock_self = make_mock_self(retries=2, max_retries=2)

    with (
        patch_sync_sessionmaker(fake_session),
        patch("engine.montecarlo.run_monte_carlo_var", side_effect=ValueError("permanent")),
        patch("tasks.var_task._emit_job_metric"),
    ):
        with pytest.raises(ValueError, match="permanent"):
            raw_task_run(mock_self, payload=PAYLOAD)

    assert len(fake_session.executed) == 1
    mock_self.retry.assert_not_called()


# ── S3 large-result offload (#130) ──────────────────────────────────────────


def test_compute_var_task_small_result_stays_inline():
    """At/below the threshold, no S3 write happens and loss_dist is untouched."""
    fake_session = FakeSyncSession()
    mock_self = make_mock_self()

    with (
        patch_sync_sessionmaker(fake_session),
        patch("engine.montecarlo.run_monte_carlo_var", return_value=MOCK_RESULT),
        patch("tasks.var_task._emit_job_metric"),
        patch("tasks.var_task.write_result_to_s3") as mock_write_s3,
    ):
        result = raw_task_run(mock_self, payload=PAYLOAD)

    mock_write_s3.assert_not_called()
    assert result["loss_dist"] == [0.0]
    assert "s3_key" not in result


def test_compute_var_task_large_result_writes_to_s3_and_strips_loss_dist():
    """Above the threshold, the full result (incl. loss_dist) is written to
    S3, and the dict returned through Celery's result backend has loss_dist
    replaced with an empty list and s3_key set to the returned key."""
    fake_session = FakeSyncSession()
    mock_self = make_mock_self()

    with (
        patch_sync_sessionmaker(fake_session),
        patch("engine.montecarlo.run_monte_carlo_var", return_value=dict(LARGE_MOCK_RESULT)),
        patch("tasks.var_task._emit_job_metric"),
        patch("tasks.var_task.write_result_to_s3", return_value="results/task-x/task-x.parquet"),
    ):
        result = raw_task_run(mock_self, payload=PAYLOAD)

    assert result["s3_key"] == "results/task-x/task-x.parquet"
    assert result["loss_dist"] == []
    # The completion audit write (#118) still only ever persists scalar
    # fields — unaffected by loss_dist/s3_key either way.
    assert len(fake_session.executed) == 1


def test_compute_var_task_s3_offload_failure_falls_back_to_inline():
    """An S3 outage on the (best-effort) offload write must not fail an
    already-successful computation — loss_dist stays inline instead."""
    fake_session = FakeSyncSession()
    mock_self = make_mock_self()

    with (
        patch_sync_sessionmaker(fake_session),
        patch("engine.montecarlo.run_monte_carlo_var", return_value=dict(LARGE_MOCK_RESULT)),
        patch("tasks.var_task._emit_job_metric"),
        patch("tasks.var_task.write_result_to_s3", side_effect=RuntimeError("simulated S3 outage")),
    ):
        result = raw_task_run(mock_self, payload=PAYLOAD)  # must not raise

    assert "s3_key" not in result
    assert result["loss_dist"] == LARGE_MOCK_RESULT["loss_dist"]
