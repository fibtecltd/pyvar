"""assistant/bank.py end to end, with fake model clients (no key, no network, no money).

Reasoning:
- The builder is run for real on the real catalogue's cases, against `FakeModelClient`, which answers from the
  record. Each test scripts one path of the pipeline: pass at once, regenerate then pass, gate flag then Opus
  fixes it, gate flag persists so static, budget stop and resume, incremental skip, a changed record.
- Tests that read a *committed* bank (portal/assistant/bank/) skip with a message while its manifest is absent:
  the bank data comes in a later change, after the paid build and a person's read of a sample.
- Nothing may put answer text in a log line or on stdout; one test looks for it in everything a build emits.
"""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Any

import pytest
import structlog.testing

from assistant import bank
from assistant import client as client_module
from assistant import prompts
from assistant.client import ModelCallError, ServedModelMismatch
from assistant.static_text import static_answer
from tests.assistant_fakes import FAITHFUL, FLAGGED, FakeModelClient

REPO = Path(__file__).resolve().parent.parent
MODELS = bank.Models(
    writer="claude-sonnet-5-5", gate="claude-opus-5-5", escalation="claude-opus-5-5"
)
SONNET, OPUS = "claude-sonnet-5-5", "claude-opus-5-5"
TODAY = lambda: datetime.date(2026, 11, 11)  # noqa: E731


@pytest.fixture(scope="module")
def all_cases() -> list[dict[str, Any]]:
    return bank.load_text_cases()


@pytest.fixture(scope="module")
def small(all_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every text case of the first three functions that have a sibling to compare with."""
    names = sorted({c["record"]["name"] for c in all_cases if c["intent"] == "compare"})[:3]
    return [c for c in all_cases if c["record"]["name"] in names]


def build(
    fake: FakeModelClient, out: Path, cases: list[dict[str, Any]], **kwargs: Any
) -> bank.BuildResult:
    options: dict[str, Any] = {"models": MODELS, "max_usd": 50.0, "today": TODAY, "cases": cases}
    options.update(kwargs)
    return bank.build(fake, out_dir=out, **options)


def load_entries(out: Path) -> dict[bank.Key, dict[str, Any]]:
    manifest = json.loads((out / "manifest.json").read_text())
    entries: dict[bank.Key, dict[str, Any]] = {}
    for path in sorted((out / manifest["bank_version"]).glob("*.json")):
        entries.update(bank.read_function_file(path.parent, path.stem))
    return entries


def keys_of(cases: list[dict[str, Any]], action: str | None = None) -> list[bank.Key]:
    return [bank.case_key(c) for c in cases if action in (None, c["intent"])]


# ── the pipeline ─────────────────────────────────────────────────────────────────────────────────────────


def test_every_answer_passes_at_once(tmp_path: Path, small: list[dict[str, Any]]) -> None:
    fake = FakeModelClient(small)
    result = build(fake, tmp_path, small)
    assert result.complete and result.stopped is None and result.built == len(small)
    assert fake.count("write") == fake.count("gate") == len(small)
    assert {(m, r) for m, r, _, _ in fake.calls} == {(SONNET, "write"), (OPUS, "gate")}
    entries = load_entries(tmp_path)
    assert sorted(entries, key=str) == sorted(keys_of(small), key=str)
    for key, entry in entries.items():
        assert set(entry) == {
            "text",
            "source",
            "writer",
            "tries",
            "escalated",
            "gate",
            "record_sha256",
        }
        assert entry["source"] == "model" and entry["writer"] == SONNET
        assert entry["tries"] == 1 and entry["escalated"] is False
        assert entry["gate"] == {"faithful": True, "issues": []}
        assert len(entry["record_sha256"]) == 64 and entry["text"] == fake.oracle(key)
    assert result.counts == {
        "model": len(small),
        "static": 0,
        "regenerated": 0,
        "escalated": 0,
        "total": len(small),
        "expected": len(small),
    }


def test_the_function_file_layout_and_the_manifest(
    tmp_path: Path, small: list[dict[str, Any]]
) -> None:
    build(FakeModelClient(small), tmp_path, small)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    version = manifest["bank_version"]
    assert manifest["prompt_version"] == prompts.PROMPT_VERSION
    assert manifest["catalogue_sha256"] == bank.catalogue_sha256()
    assert manifest["grader_sha256"] == bank.grader_sha256()
    assert manifest["models"] == {"writer": SONNET, "gate": OPUS, "escalation": OPUS}
    assert manifest["built"] == "2026-11-11" and manifest["complete"] is True
    assert manifest["counts"]["model"] == len(small) and manifest["stopped"] is None
    name = small[0]["record"]["name"]
    body = json.loads((tmp_path / version / f"{name}.json").read_text())
    assert set(body) == {"explain", "when", "compare"}
    ((sibling, entry),) = body["compare"].items()
    assert (
        sibling
        == next(c for c in small if c["intent"] == "compare" and c["record"]["name"] == name)[
            "other"
        ]["name"]
    )
    assert entry["source"] == "model"
    assert not list(tmp_path.rglob("*.tmp"))


def test_the_bank_version_is_the_prompt_version_and_eight_characters_of_the_catalogue_hash() -> (
    None
):
    digest = bank.catalogue_sha256()
    assert bank.bank_version(digest) == f"{prompts.PROMPT_VERSION}-{digest[:8]}"
    assert bank.bank_version("f" * 64) == f"{prompts.PROMPT_VERSION}-ffffffff"
    assert len(digest) == 64


def test_a_grader_failure_sends_its_flags_back_and_the_second_draft_passes(
    tmp_path: Path, small: list[dict[str, Any]]
) -> None:
    target = keys_of(small, "when")[0]
    fake = FakeModelClient(
        small,
        write=lambda key, attempt, model, request: (
            "Too short." if key == target and attempt == 0 else fake.oracle(key)
        ),
    )
    result = build(fake, tmp_path, small)
    assert result.complete and result.counts["regenerated"] == 1
    entry = load_entries(tmp_path)[target]
    assert entry["tries"] == 2 and entry["source"] == "model" and entry["escalated"] is False
    retry = next(
        r
        for r, (_, role, key, attempt) in zip(fake.requests, fake.calls)
        if key == target and attempt == 1 and role == "write"
    )
    assert [m["role"] for m in retry["messages"]] == ["user", "assistant", "user"]
    assert retry["messages"][1]["content"] == "Too short."
    correction = retry["messages"][2]["content"]
    assert "That answer failed these checks" in correction and "length" in correction
    assert fake.count("gate") == len(small)  # the gate saw the final text once


def test_a_reply_that_never_names_the_function_is_told_to(
    tmp_path: Path, small: list[dict[str, Any]]
) -> None:
    target = keys_of(small, "explain")[0]
    vague = "This computes a measure that risk teams use every day to size their exposure. " * 3
    fake = FakeModelClient(
        small,
        write=lambda key, attempt, model, request: (
            vague if key == target and attempt == 0 else fake.oracle(key)
        ),
    )
    build(fake, tmp_path, small)
    retry = next(
        r
        for r, (_, role, key, attempt) in zip(fake.requests, fake.calls)
        if key == target and attempt == 1 and role == "write"
    )
    assert "name the function" in retry["messages"][-1]["content"]


def test_three_failed_drafts_give_static_text_and_no_gate_call(
    tmp_path: Path, small: list[dict[str, Any]]
) -> None:
    target = keys_of(small, "explain")[0]
    case = next(c for c in small if bank.case_key(c) == target)
    fake = FakeModelClient(
        small,
        write=lambda key, attempt, model, request: ("No." if key == target else fake.oracle(key)),
    )
    result = build(fake, tmp_path, small)
    entry = load_entries(tmp_path)[target]
    assert entry["source"] == "static" and entry["writer"] == "static" and entry["tries"] == 3
    assert entry["text"] == static_answer(case) and entry["gate"] == {
        "faithful": None,
        "issues": [],
    }
    assert entry["escalated"] is False
    assert sum(1 for _, role, key, _ in fake.calls if key == target and role == "gate") == 0
    assert sum(1 for _, role, key, _ in fake.calls if key == target and role == "write") == 3
    assert result.counts["static"] == 1 and result.counts["regenerated"] == 1


def test_a_truncated_reply_counts_as_a_failed_draft(
    tmp_path: Path, small: list[dict[str, Any]]
) -> None:
    target = keys_of(small, "when")[0]
    fake = FakeModelClient(
        small,
        stop_reason=lambda key, attempt, model: (
            "max_tokens" if key == target and attempt == 0 else "end_turn"
        ),
    )
    build(fake, tmp_path, small)
    entry = load_entries(tmp_path)[target]
    assert entry["tries"] == 2
    retry = next(
        r
        for r, (_, role, key, attempt) in zip(fake.requests, fake.calls)
        if key == target and attempt == 1 and role == "write"
    )
    assert "cut off at the token limit" in retry["messages"][-1]["content"]


def test_a_gate_flag_is_rewritten_once_by_opus_and_the_rewrite_is_gated_again(
    tmp_path: Path, small: list[dict[str, Any]]
) -> None:
    target = keys_of(small, "when")[0]
    models = bank.Models(writer=SONNET, gate=OPUS, escalation="claude-opus-5-5")
    fake = FakeModelClient(
        small,
        judge=lambda key, attempt, model, request: (
            FLAGGED if key == target and attempt == 0 else FAITHFUL
        ),
    )
    result = build(fake, tmp_path, small, models=models)
    entry = load_entries(tmp_path)[target]
    assert entry["source"] == "model" and entry["escalated"] is True and entry["writer"] == OPUS
    assert entry["gate"]["faithful"] is True
    seen = [(m, role, attempt) for m, role, key, attempt in fake.calls if key == target]
    assert seen == [
        (SONNET, "write", 0),
        (OPUS, "gate", 0),
        (OPUS, "write", 0),  # the rewrite
        (OPUS, "gate", 1),
    ]
    rewrite_request = next(
        r
        for r, (m, role, key, _) in zip(fake.requests, fake.calls)
        if key == target and role == "write" and m == OPUS
    )
    last = rewrite_request["messages"][-1]["content"]
    assert "a reviewer found: says the function fits a model it only filters" in last
    assert result.counts["escalated"] == 1 and result.counts["static"] == 0


def test_a_gate_flag_that_persists_gives_static_text(
    tmp_path: Path, small: list[dict[str, Any]]
) -> None:
    target = keys_of(small, "explain")[1]
    case = next(c for c in small if bank.case_key(c) == target)
    fake = FakeModelClient(
        small, judge=lambda key, attempt, model, request: FLAGGED if key == target else FAITHFUL
    )
    result = build(fake, tmp_path, small)
    entry = load_entries(tmp_path)[target]
    assert entry["source"] == "static" and entry["escalated"] is True and entry["tries"] == 1
    assert entry["text"] == static_answer(case)
    assert sum(1 for _, role, key, _ in fake.calls if key == target and role == "gate") == 2
    assert result.counts["static"] == 1 and result.counts["escalated"] == 1


def test_an_unusable_rewrite_goes_static_without_a_second_gate_call(
    tmp_path: Path, small: list[dict[str, Any]]
) -> None:
    target = keys_of(small, "explain")[0]
    case = next(c for c in small if bank.case_key(c) == target)

    def write(key: bank.Key, attempt: int, model: str, request: dict[str, Any]) -> str:
        return (
            "Not a good answer."
            if key == target and len(request["messages"]) > 1
            else fake.oracle(key)
        )

    fake = FakeModelClient(
        small,
        write=write,
        judge=lambda key, attempt, model, request: FLAGGED if key == target else FAITHFUL,
    )
    build(fake, tmp_path, small)
    entry = load_entries(tmp_path)[target]
    assert entry["source"] == "static" and entry["text"] == static_answer(case)
    assert sum(1 for _, role, key, _ in fake.calls if key == target and role == "gate") == 1


def test_an_unreadable_gate_reply_is_asked_again_then_treated_as_a_flag(
    tmp_path: Path, small: list[dict[str, Any]]
) -> None:
    target = keys_of(small, "when")[0]
    fake = FakeModelClient(
        small,
        judge=lambda key, attempt, model, request: (
            "I cannot say." if key == target and attempt < 2 else FAITHFUL
        ),
    )
    build(fake, tmp_path, small)
    entry = load_entries(tmp_path)[target]
    assert entry["escalated"] is True and entry["source"] == "model"
    assert sum(1 for _, role, key, _ in fake.calls if key == target and role == "gate") == 3


# ── money, resume, incremental ───────────────────────────────────────────────────────────────────────────


def test_the_budget_stops_the_build_before_it_is_exceeded_and_a_second_run_finishes(
    tmp_path: Path, small: list[dict[str, Any]]
) -> None:
    first = FakeModelClient(small)
    result = build(first, tmp_path, small, max_usd=0.15)
    assert not result.complete and result.stopped == "budget"
    assert result.cost_usd <= 0.15 and 0 < result.built < len(small)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["complete"] is False and manifest["stopped"] == "budget"
    assert manifest["counts"]["total"] == result.built
    second = FakeModelClient(small)
    finished = build(second, tmp_path, small, max_usd=50)
    assert finished.complete and finished.reused == result.built
    # Only the answer being written when the cap bit is written twice: its draft was paid for, then the gate
    # call did not fit. Everything finished before that is reused.
    assert first.count("write") + second.count("write") == len(small) + 1
    assert second.count("write") == len(small) - result.built
    assert json.loads((tmp_path / "manifest.json").read_text())["complete"] is True


def test_a_zero_budget_makes_no_call(tmp_path: Path, small: list[dict[str, Any]]) -> None:
    fake = FakeModelClient(small)
    result = build(fake, tmp_path, small, max_usd=0.0)
    assert fake.calls == [] and result.stopped == "budget" and not result.complete
    assert json.loads((tmp_path / "manifest.json").read_text())["complete"] is False


def test_the_reserved_estimate_is_never_below_what_a_call_costs(
    small: list[dict[str, Any]],
) -> None:
    fake = FakeModelClient(small)
    for case in small:
        request = prompts.build_request(case)
        reply = fake.complete(SONNET, request)
        assert bank.estimate_cost(SONNET, request) >= reply.cost


def test_a_second_run_with_nothing_changed_makes_no_call(
    tmp_path: Path, small: list[dict[str, Any]]
) -> None:
    build(FakeModelClient(small), tmp_path, small)
    before = {p.name: p.read_bytes() for p in tmp_path.rglob("*.json") if p.name != "manifest.json"}
    again = FakeModelClient(small)
    result = build(again, tmp_path, small)
    assert again.calls == [] and result.reused == len(small) and result.built == 0
    assert result.complete
    after = {p.name: p.read_bytes() for p in tmp_path.rglob("*.json") if p.name != "manifest.json"}
    assert after == before  # the manifest differs only by this run's cost


def test_a_changed_grader_hash_or_prompt_version_rebuilds_everything(
    tmp_path: Path, small: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    build(FakeModelClient(small), tmp_path, small)
    monkeypatch.setattr(bank, "grader_sha256", lambda: "0" * 64)
    again = FakeModelClient(small)
    build(again, tmp_path, small)
    assert again.count("write") == len(small)
    monkeypatch.setattr(prompts, "PROMPT_VERSION", "v9-test")
    third = FakeModelClient(small)
    result = build(third, tmp_path, small)
    assert third.count("write") == len(small) and result.bank_version.startswith("v9-test-")


def edited_catalogue(tmp_path: Path, name: str) -> Path:
    entries = json.loads(bank.CATALOGUE_PATH.read_text())
    for entry in entries:
        if entry["name"] == name:
            entry["summary"] = entry["summary"] + " Edited for the test."
    path = tmp_path / "functions.json"
    path.write_text(json.dumps(entries))
    return path


def test_a_catalogue_edit_starts_a_new_version_and_rebuilds_only_the_changed_answers(
    tmp_path: Path, small: list[dict[str, Any]], all_cases: list[dict[str, Any]]
) -> None:
    out = tmp_path / "bank"
    first = build(FakeModelClient(small), out, small)
    name = small[0]["record"]["name"]
    new_catalogue = edited_catalogue(tmp_path, name)
    new_all = bank.load_text_cases(new_catalogue)
    new_small = [c for c in new_all if c["record"]["name"] in {x["record"]["name"] for x in small}]
    old_hash = {bank.case_key(c): bank.record_sha256(c) for c in small}
    changed = {
        k
        for k, h in ((bank.case_key(c), bank.record_sha256(c)) for c in new_small)
        if h != old_hash[k]
    }
    assert changed and len(changed) < len(small)
    fake = FakeModelClient(new_small)
    result = build(fake, out, new_small, catalogue_path=new_catalogue)
    assert result.bank_version != first.bank_version and result.complete
    rebuilt = {key for _, role, key, _ in fake.calls if role == "write"}
    assert rebuilt == changed and result.reused == len(small) - len(changed)
    assert (out / first.bank_version).is_dir() and (out / result.bank_version).is_dir()
    assert len(list((out / result.bank_version).glob("*.json"))) == len({k[0] for k in old_hash})


def test_only_functions_limits_a_build_and_leaves_the_bank_incomplete(
    tmp_path: Path, small: list[dict[str, Any]]
) -> None:
    only = small[0]["record"]["name"]
    fake = FakeModelClient(small)
    result = build(fake, tmp_path, small, only_functions={only})
    assert {key[0] for _, _, key, _ in fake.calls} == {only}
    assert not result.complete and result.missing == sum(
        1 for c in small if c["record"]["name"] != only
    )
    # the other functions are then built by a run without the filter, the first stays as it is
    rest = FakeModelClient(small)
    assert build(rest, tmp_path, small).complete
    assert only not in {key[0] for _, _, key, _ in rest.calls}


def test_static_entries_are_kept_unless_retry_static_is_set(
    tmp_path: Path, small: list[dict[str, Any]]
) -> None:
    target = keys_of(small, "explain")[0]
    bad = FakeModelClient(small, write=lambda k, a, m, r: "No." if k == target else bad.oracle(k))
    build(bad, tmp_path, small)
    assert load_entries(tmp_path)[target]["source"] == "static"
    kept = FakeModelClient(small)
    build(kept, tmp_path, small)
    assert kept.calls == []
    retried = FakeModelClient(small)
    result = build(retried, tmp_path, small, retry_static=True)
    assert {key for _, _, key, _ in retried.calls} == {target}
    assert load_entries(tmp_path)[target]["source"] == "model" and result.counts["static"] == 0


def test_a_failed_model_call_skips_that_answer_and_the_next_run_builds_it(
    tmp_path: Path, small: list[dict[str, Any]]
) -> None:
    target = keys_of(small, "when")[0]
    flaky = FakeModelClient(
        small, fail=lambda m, role, key: ModelCallError("down") if key == target else None
    )
    result = build(flaky, tmp_path, small)
    assert result.failed == 1 and result.missing == 1 and not result.complete
    assert target not in load_entries(tmp_path)
    healthy = FakeModelClient(small)
    assert build(healthy, tmp_path, small).complete
    assert {key for _, role, key, _ in healthy.calls if role == "write"} == {target}


def test_too_many_failed_calls_stop_the_build(
    tmp_path: Path, all_cases: list[dict[str, Any]]
) -> None:
    down = FakeModelClient(all_cases, fail=lambda m, role, key: ModelCallError("down"))
    result = build(down, tmp_path, all_cases[:40])
    assert result.stopped == "errors" and result.failed == bank.MAX_CALL_FAILURES
    assert len(down.calls) == bank.MAX_CALL_FAILURES


def test_a_served_model_mismatch_stops_the_build_and_leaves_the_manifest_incomplete(
    tmp_path: Path, small: list[dict[str, Any]]
) -> None:
    wrong = FakeModelClient(small, fail=lambda m, role, key: ServedModelMismatch("served by x"))
    with pytest.raises(ServedModelMismatch):
        build(wrong, tmp_path, small)
    assert json.loads((tmp_path / "manifest.json").read_text())["complete"] is False


def test_a_model_without_a_price_is_refused_before_any_call(
    tmp_path: Path, small: list[dict[str, Any]]
) -> None:
    fake = FakeModelClient(small)
    with pytest.raises(ValueError, match="no price"):
        build(fake, tmp_path, small, models=bank.Models("claude-nope", OPUS, OPUS))
    assert fake.calls == [] and not (tmp_path / "manifest.json").exists()


# ── files ────────────────────────────────────────────────────────────────────────────────────────────────


def test_a_failed_write_leaves_the_old_file_intact_and_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "bank" / "f.json"
    bank._atomic_write(target, "old\n")

    def boom(src: str, dst: Path) -> None:
        raise OSError("disk went away")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        bank._atomic_write(target, "new\n")
    monkeypatch.undo()
    assert target.read_text() == "old\n"
    assert [p.name for p in target.parent.iterdir()] == ["f.json"]


def test_a_crash_mid_build_leaves_only_whole_files_and_an_incomplete_manifest(
    tmp_path: Path, small: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    real = bank._atomic_write
    count = {"n": 0}

    def crash_on_second_function(path: Path, content: str) -> None:
        if path.name != "manifest.json":
            count["n"] += 1
            if count["n"] == 2:
                raise OSError("killed")
        real(path, content)

    monkeypatch.setattr(bank, "_atomic_write", crash_on_second_function)
    with pytest.raises(OSError):
        build(FakeModelClient(small), tmp_path, small)
    monkeypatch.undo()
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["complete"] is False
    written = list((tmp_path / manifest["bank_version"]).glob("*.json"))
    assert len(written) == 1 and json.loads(written[0].read_text())  # whole, parseable
    assert not list(tmp_path.rglob("*.tmp"))
    resumed = FakeModelClient(small)
    assert build(resumed, tmp_path, small).complete
    assert written[0].stem not in {key[0] for _, _, key, _ in resumed.calls}


def test_a_build_with_one_worker_and_with_four_write_the_same_files(
    tmp_path: Path, all_cases: list[dict[str, Any]]
) -> None:
    subset = all_cases[:90]
    build(FakeModelClient(subset), tmp_path / "one", subset, workers=1)
    build(FakeModelClient(subset), tmp_path / "four", subset, workers=4)
    one = {
        p.relative_to(tmp_path / "one"): p.read_bytes() for p in (tmp_path / "one").rglob("*.json")
    }
    four = {
        p.relative_to(tmp_path / "four"): p.read_bytes()
        for p in (tmp_path / "four").rglob("*.json")
    }
    assert one == four and len(one) > 20


# ── check ────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def built(tmp_path: Path, small: list[dict[str, Any]]) -> Path:
    build(FakeModelClient(small), tmp_path, small)
    return tmp_path


def run_check(out: Path, cases: list[dict[str, Any]], **kwargs: Any) -> bank.CheckReport:
    return bank.check(out, cases=cases, **kwargs)


def test_check_passes_a_good_bank_and_reports_its_size(
    built: Path, small: list[dict[str, Any]]
) -> None:
    report = run_check(built, small)
    assert report.ok, report.problems
    assert report.entries == len(small) and report.files == 3 and report.static == 0
    assert 0 < report.largest_file <= report.bytes <= bank.MAX_BANK_BYTES


def edit_entry(out: Path, key: bank.Key, **changes: Any) -> None:
    manifest = json.loads((out / "manifest.json").read_text())
    path = out / manifest["bank_version"] / f"{key[0]}.json"
    entries = bank.read_function_file(path.parent, key[0])
    entries[key].update(changes)
    path.write_text(json.dumps(bank.entries_to_file(entries)))


def test_check_names_the_function_whose_record_changed(
    built: Path, small: list[dict[str, Any]], tmp_path_factory: pytest.TempPathFactory
) -> None:
    name = small[0]["record"]["name"]
    new_catalogue = edited_catalogue(tmp_path_factory.mktemp("cat"), name)
    new_cases = [
        c
        for c in bank.load_text_cases(new_catalogue)
        if c["record"]["name"] in {x["record"]["name"] for x in small}
    ]
    report = bank.check(built, catalogue_path=new_catalogue, cases=new_cases)
    assert not report.ok
    text = "\n".join(report.problems)
    assert f"{name}:explain: the record changed" in text
    assert "manifest catalogue_sha256" in text and "manifest bank_version" in text
    others = [p for p in report.problems if "the record changed" in p]
    assert all(p.split(":")[0] in {x["record"]["name"] for x in small} for p in others)


def test_check_regrades_every_served_answer(built: Path, small: list[dict[str, Any]]) -> None:
    key = keys_of(small, "when")[0]
    edit_entry(built, key, text="Short and without the function.")
    problems = run_check(built, small).problems
    assert any(p.startswith(f"{key[0]}:when: no longer passes the graders") for p in problems)


def test_check_rejects_a_hand_edited_static_answer_and_an_ungated_model_answer(
    built: Path, small: list[dict[str, Any]]
) -> None:
    keys = keys_of(small, "explain")
    summary = next(c for c in small if bank.case_key(c) == keys[0])["record"]["summary"]
    edit_entry(built, keys[0], source="static", writer="static", text=summary * 3)
    edit_entry(built, keys[1], gate={"faithful": None, "issues": []})
    problems = "\n".join(run_check(built, small).problems)
    assert (
        f"{keys[0][0]}:explain: static text differs from the text built from the record" in problems
    )
    assert f"{keys[1][0]}:explain: a model answer without a faithful gate verdict" in problems


def test_check_finds_a_missing_answer_a_missing_manifest_and_an_incomplete_one(
    built: Path, small: list[dict[str, Any]]
) -> None:
    manifest = json.loads((built / "manifest.json").read_text())
    victim = small[0]["record"]["name"]
    (built / manifest["bank_version"] / f"{victim}.json").unlink()
    problems = run_check(built, small).problems
    assert f"{victim}:explain: no answer in the bank" in problems
    manifest["complete"] = False
    (built / "manifest.json").write_text(json.dumps(manifest))
    assert "manifest says complete=false" in run_check(built, small).problems
    (built / "manifest.json").unlink()
    assert "missing" in run_check(built, small).problems[0]


def test_check_bounds_the_size_of_a_file_and_of_the_bank(
    built: Path, small: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bank, "MAX_FILE_BYTES", 500)
    monkeypatch.setattr(bank, "MAX_BANK_BYTES", 1000)
    problems = "\n".join(run_check(built, small).problems)
    assert "bytes, over 500" in problems and "the bank is" in problems


def test_check_fails_a_bank_with_three_percent_static_answers(
    tmp_path: Path, small: list[dict[str, Any]]
) -> None:
    build(FakeModelClient(small, judge=lambda *a: FLAGGED), tmp_path, small)
    report = run_check(tmp_path, small)
    assert report.static == len(small)
    assert any("static answers are" in p and "not under 3%" in p for p in report.problems)


def test_check_flags_a_stray_file(built: Path, small: list[dict[str, Any]]) -> None:
    manifest = json.loads((built / "manifest.json").read_text())
    (built / manifest["bank_version"] / "not_a_function.json").write_text("{}")
    assert any("not a function of the catalogue" in p for p in run_check(built, small).problems)


def test_check_flags_a_prompt_edited_without_a_version_bump(
    built: Path, small: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prompts, "SYSTEM_PROMPT", prompts.SYSTEM_PROMPT + " Be brief.")
    assert any("manifest prompt_sha256" in p for p in run_check(built, small).problems)


# ── logs ─────────────────────────────────────────────────────────────────────────────────────────────────


def test_no_answer_text_reaches_a_log_line_or_stdout(
    tmp_path: Path,
    small: list[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    flagged = keys_of(small, "when")[0]
    fake = FakeModelClient(
        small,
        write=lambda key, attempt, model, request: (
            "A draft that is far too short."
            if key == flagged and attempt == 0
            else fake.oracle(key)
        ),
        judge=lambda key, attempt, model, request: (
            FLAGGED if key == flagged and attempt == 0 else FAITHFUL
        ),
    )
    with structlog.testing.capture_logs() as events:
        build(fake, tmp_path, small)
    texts = [e["text"] for e in load_entries(tmp_path).values()] + [
        "A draft that is far too short."
    ]
    emitted = json.dumps(events, default=str) + capsys.readouterr().out + caplog.text
    assert events, "the build should log"
    for text in texts:
        assert text[:40] not in emitted
    assert {k for e in events for k in e} <= {
        "event",
        "log_level",
        "function",
        "action",
        "sibling",
        "source",
        "tries",
        "escalated",
        "faithful",
        "bank_version",
        "complete",
        "stopped",
        "cost_usd",
        "entries",
        "expected",
        "error",
    }


# ── the whole catalogue, and the command line ────────────────────────────────────────────────────────────


def test_a_full_bank_of_oracle_answers_builds_and_passes_check(
    tmp_path: Path, all_cases: list[dict[str, Any]]
) -> None:
    fake = FakeModelClient(all_cases)
    result = build(fake, tmp_path, all_cases, workers=4)
    assert result.complete and result.counts["total"] == 1154 == result.counts["expected"]
    assert len(all_cases) == 1154 and len({bank.case_key(c) for c in all_cases}) == 1154
    report = bank.check(tmp_path, cases=all_cases)
    assert report.ok, report.problems[:5]
    assert report.files == 385 and report.entries == 1154
    assert report.largest_file < bank.MAX_FILE_BYTES


def test_the_command_line_checks_without_a_client(
    built: Path,
    small: list[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bank, "load_text_cases", lambda path=bank.CATALOGUE_PATH: small)
    assert bank.main(["check", "--out", str(built)]) == 0
    assert "entries 9" in capsys.readouterr().out
    key = keys_of(small, "when")[0]
    edit_entry(built, key, text="Short.")
    assert bank.main(["check", "--out", str(built)]) == 1
    out = capsys.readouterr().out
    assert "PROBLEM" in out and "Short." not in out


def test_the_command_line_builds_with_the_configured_models_and_needs_a_cap(
    tmp_path: Path,
    small: list[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeModelClient(small)
    monkeypatch.setattr(bank, "load_text_cases", lambda path=bank.CATALOGUE_PATH: small)
    monkeypatch.setattr(client_module, "AnthropicClient", lambda: fake)
    out = str(tmp_path / "bank")
    with pytest.raises(SystemExit):
        bank.main(["build", "--out", out])  # --max-usd is required
    code = bank.main(["build", "--out", out, "--max-usd", "5", "--workers", "1"])
    assert code == 0 and "complete=True" in capsys.readouterr().out
    assert {m for m, _, _, _ in fake.calls} == {SONNET, OPUS}
    only = small[0]["record"]["name"]
    again = bank.main(
        ["build", "--out", str(tmp_path / "b2"), "--max-usd", "5", "--only-functions", only]
    )
    assert again == 1  # the other functions are missing, so not complete


# ── a committed bank, once there is one ──────────────────────────────────────────────────────────────────

COMMITTED = REPO / "portal" / "assistant" / "bank"
needs_bank = pytest.mark.skipif(
    not (COMMITTED / "manifest.json").exists(),
    reason=(
        "no committed bank yet: portal/assistant/bank/manifest.json is absent "
        "(the bank data comes in a later PR, after the paid build and a person's read of a sample)"
    ),
)


@needs_bank
def test_the_committed_bank_matches_the_catalogue_the_graders_and_the_prompt() -> None:
    report = bank.check(COMMITTED)
    assert report.ok, "run `python -m assistant.bank build`:\n" + "\n".join(report.problems[:20])


@needs_bank
def test_the_committed_manifest_is_complete_and_names_its_directory() -> None:
    manifest = json.loads((COMMITTED / "manifest.json").read_text())
    assert manifest["complete"] is True
    assert (COMMITTED / manifest["bank_version"]).is_dir()
    assert manifest["bank_version"] == bank.bank_version(manifest["catalogue_sha256"])
