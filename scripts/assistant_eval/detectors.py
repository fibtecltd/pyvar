"""Known-error detectors for the 8 cases Opus keeps flagging (plan 1, section 6 control 1; section 3 item 9).

Reasoning:
- Eight menu cases were flagged by Opus on two or more of four draws (docs/assistant-phase0-results.md 9.14).
  Opus judging an Opus-written answer is self-grading (plan section 6), so a writer that stops making the
  known wrong claim must be visible without a model grading it. These detectors read a written answer and
  say whether it makes that claim: deterministic, regex or record-fact checks, no model, no network.
- Each detector names the claim, the record fact that contradicts it, and its evidence level:
  * "recorded": the claim is described in the results document (9.10, 9.12, 9.14, 9.16, section 4/6);
  * "hypothesis": the repository records only that Opus flagged the case, not what it flagged (the flags CSVs
    hold F/P and the grader failure, not Opus's issue text), so the detector tests a misreading the record
    makes easy. It is a candidate, not a measurement of the flagged claim; read the flags before relying on it.
- A detector is a sentence-level pattern: it can miss a paraphrase (a clean result is not proof of a correct
  answer) and it can fire on a loosely worded but correct sentence. Both directions are tested on written
  examples (tests/test_assistant_detectors.py); the record-built oracle text must trigger none.

Usage:
    python scripts/assistant_eval/detectors.py --cases CASES --run DIR [--run DIR ...] [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_FLAGS = re.IGNORECASE


def sentences(text: str) -> list[str]:
    """Sentences and bullet lines of an answer."""
    return [part.strip() for part in _SPLIT.split(text) if part.strip()]


def _aliases(case: dict[str, Any], param: str, extra: tuple[str, ...] = ()) -> list[str]:
    """How an answer may refer to a parameter: its name, the name in words, its symbol, extras."""
    record = case["record"]
    names = [param, param.replace("_", " "), *extra]
    symbol = re.sub(r"[^A-Za-z]", "", str((record.get("symbol_map") or {}).get(param, "")))
    if len(symbol) >= 3:
        names.append(symbol)
    return [n.lower() for n in names]


def _says(sentence: str, names: list[str]) -> bool:
    low = sentence.lower()
    return any(n in low for n in names)


def _hits(text: str, test: Callable[[str], bool]) -> list[str]:
    return [s for s in sentences(text) if test(s)]


def _mentioning(text: str, names: list[str], pattern: re.Pattern[str]) -> list[str]:
    """Sentences that refer to one of `names` and match `pattern`."""
    return [s for s in sentences(text) if _says(s, names) and pattern.search(s)]


# ── generic record-fact checks ─────────────────────────────────────────────────────────────────────

_OPTIONAL = re.compile(
    r"\b(?:optional(?:ly)?|if (?:you )?(?:have|has|supply|supplied|provide|provided|available|needed)|"
    r"when available|(?:can|may|could) (?:omit|skip|leave)|leave (?:it |them )?out|omit|"
    r"without (?:supplying|providing)|not (?:required|needed|mandatory|necessary))\b",
    _FLAGS,
)
_UNSURE = re.compile(
    r"\b(?:unclear|not clear|uncertain|not (?:specified|stated)|isn['’]t (?:specified|stated)|"
    r"(?:doesn['’]t|does not) (?:say|specify|state)|cannot tell|can['’]t tell)\b",
    _FLAGS,
)


def required_called_optional(
    text: str, case: dict[str, Any], extra: dict[str, tuple[str, ...]] | None = None
) -> list[str]:
    """Sentences that call a parameter the record marks required optional."""
    extra = extra or {}
    required = [p["name"] for p in case["record"]["parameters"] if p["required"]]
    out: list[str] = []
    for param in required:
        names = _aliases(case, param, extra.get(param, ()))
        out += _mentioning(text, names, _OPTIONAL)
    return sorted(set(out))


def unsure_about_a_parameter(text: str, case: dict[str, Any]) -> list[str]:
    """Sentences that say it is unclear what a parameter of the record is or does."""
    out: list[str] = []
    for param in case["record"]["parameters"]:
        names = _aliases(case, param["name"])[:2]
        out += _mentioning(text, names, _UNSURE)
    return sorted(set(out))


def sibling_overreach(
    text: str, case: dict[str, Any], sibling_pattern: str, vocabulary: str
) -> list[str]:
    """Sentences naming a sibling (matched by `sibling_pattern`) that give it a capability from `vocabulary`
    which the sibling's listing does not mention."""
    listings = " ".join(
        f"{s['name']} {s['summary']}"
        for s in case.get("siblings") or []
        if re.search(sibling_pattern, s["name"], _FLAGS)
    ).lower()
    claim = re.compile(vocabulary, _FLAGS)
    named = re.compile(sibling_pattern, _FLAGS)

    def test(sentence: str) -> bool:
        return bool(named.search(sentence)) and any(
            m.group(0).lower() not in listings for m in claim.finditer(sentence)
        )

    return _hits(text, test)


# ── the detectors ──────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Detector:
    case_id: str
    key: str
    claim: str
    fact: str
    evidence: str  # "recorded: <where>" or "hypothesis: <why>"
    find: Callable[[str, dict[str, Any]], list[str]]


def _pillar(text: str, case: dict[str, Any]) -> list[str]:
    return required_called_optional(
        text,
        case,
        {
            "risk_addons": ("add-on", "addon"),
            "risk_weighted_assets": ("risk-weighted assets", "risk weighted assets"),
        },
    )


_REVALUE_AGENT = re.compile(
    r"\b(?:pyvar|the function|this function|it|the tool)\s+(?:(?:will|should|can|must|does|then|first|also)\s+)*"
    r"(?:re-?values?|re-?prices?|revalues|re-?runs|(?:computes|calculates|derives|produces|generates) the "
    r"(?:three |shocked |base )?(?:present values|pvs|valuations))\b|"
    r"\bre-?valued\s+(?:by|inside|within|in)\s+(?:pyvar|the function|this function)\b",
    _FLAGS,
)
_NOTIONAL = ("notional",)
_FORWARD_RATE = re.compile(r"\bforward (?:rate|price|curve)\b|\bthe forward\b", _FLAGS)
_AFFECTS = re.compile(
    r"\b(?:scales?|affects?|sets?|drives?|determines?|changes?|moves?|multipl\w+|adjusts?|shifts?)\b",
    _FLAGS,
)
_NOT_AFFECT = re.compile(
    r"\b(?:does not|doesn['’]t|no effect|not affect|unaffected|independent|only)\b", _FLAGS
)
_GIVES_VALUE = re.compile(
    r"\b(?:gives?|yields?|returns?|produces?|provides?|determines?|computes?|calculates?)\b[^.]*"
    r"\b(?:value|mark-to-market|mtm|p&l|worth)\b|\bvalue (?:of|for) (?:the|your|a) (?:position|trade|forward)\b",
    _FLAGS,
)
_HAS_CONTRACT = re.compile(r"\bcontract|\bonly\b|\bif\b|\bwhen\b|\bsupplied\b|\bprovided\b", _FLAGS)


def _fx_forward(text: str, case: dict[str, Any]) -> list[str]:
    del case

    def affects_forward(s: str) -> bool:
        return (
            _says(s, ["notional"])
            and bool(_FORWARD_RATE.search(s))
            and bool(_AFFECTS.search(s))
            and not _NOT_AFFECT.search(s)
        )

    def value_without_contract(s: str) -> bool:
        return (
            _says(s, ["notional"]) and bool(_GIVES_VALUE.search(s)) and not _HAS_CONTRACT.search(s)
        )

    return sorted(set(_hits(text, affects_forward) + _hits(text, value_without_contract)))


_EPE_PEAK = re.compile(
    r"\b(?:peak|maximum|max|worst[- ]case|upper bound|highest|99(?:\.\d+)?%|percentile|quantile|pfe)\b",
    _FLAGS,
)


def _cva(text: str, case: dict[str, Any]) -> list[str]:
    epe = _hits(
        text,
        lambda s: _says(s, ["expected_positive_exposure_epe", "expected positive exposure"])
        and bool(_EPE_PEAK.search(s)),
    )
    return sorted(set(unsure_about_a_parameter(text, case) + epe))


_BETTER = re.compile(r"\b(?:better|safer|healthier|stronger|good|lower risk|less risk)\b", _FLAGS)
_HIGHER = re.compile(r"\bhigher\b|\bhigh\b|\bincreases?\b|\brises?\b", _FLAGS)
_AVERAGE = re.compile(r"\b(?:averag\w+|mean|weighted|product|multipl\w+|divid\w+)\b", _FLAGS)
_MORE_RISK = re.compile(
    r"\b(?:raises?|increases?|higher (?:risk|tier)|more risk|worse|adds? to)\b", _FLAGS
)


def _conduct_vs_model_risk(text: str, case: dict[str, Any]) -> list[str]:
    del case

    def direction(s: str) -> bool:
        return (
            _says(s, ["conduct"])
            and bool(_HIGHER.search(s))
            and bool(_BETTER.search(s))
            and not re.search(r"\bnot\b|\bworse\b", s, _FLAGS)
        )

    def averaged(s: str) -> bool:
        return _says(s, ["complaint", "redress"]) and bool(_AVERAGE.search(s))

    def validation_raises_risk(s: str) -> bool:
        return (
            _says(s, ["validation"])
            and bool(re.search(r"\bhigher\b|\bstronger\b|\bbetter\b", s, _FLAGS))
            and bool(_MORE_RISK.search(s))
            and not re.search(r"\blower|reduc|discount|less\b", s, _FLAGS)
        )

    return sorted(
        set(_hits(text, direction) + _hits(text, averaged) + _hits(text, validation_raises_risk))
    )


def _black_scholes(text: str, case: dict[str, Any]) -> list[str]:
    return sibling_overreach(
        text,
        case,
        r"tree|binomial|trinomial",
        r"American|Bermudan|path[- ]dependent|barrier|exotic|early[- ]exercise|Asian|lookback|callable",
    )


_NO_RATES = re.compile(
    r"\b(?:no|not|without|never|omits?|lacks?)\b[^.]*\b(?:rate values|run-?off rates|specific rates|"
    r"default rates|rate figures|category rates|rates? (?:are|is) (?:given|provided|listed|specified))\b",
    _FLAGS,
)


def _retail(text: str, case: dict[str, Any]) -> list[str]:
    del case
    return _hits(
        text, lambda s: bool(_NO_RATES.search(s)) and not _says(s, ["you supply", "you provide"])
    )


_OPTIMISE = re.compile(
    r"\b(?:re-?optimi[sz]\w*|optimi[sz]\w*|tilt\w*|minimum[- ]variance|rebalanc\w*)\b", _FLAGS
)
_COVARIANCE = ("cov_matrix", "covariance", "cov matrix")


def _esg(text: str, case: dict[str, Any]) -> list[str]:
    del case

    def floor_alone(s: str) -> bool:
        return (
            _says(s, ["min_esg_score", "minimum esg", "esg floor"])
            and bool(_OPTIMISE.search(s))
            and not _says(s, list(_COVARIANCE))
        )

    def maximises(s: str) -> bool:
        return bool(
            re.search(r"\bmaximi[sz]\w*\b[^.]*\besg\b|\besg\b[^.]*\bmaximi[sz]\w*\b", s, _FLAGS)
        )

    return sorted(set(_hits(text, floor_alone) + _hits(text, maximises)))


DETECTORS: list[Detector] = [
    Detector(
        "pillar_2a_capital:when",
        "required_input_called_optional",
        "calls a required input (risk_addons, risk_weighted_assets) optional",
        "both parameters are required; the ratio needs risk_weighted_assets",
        "recorded: results 9.14 (calls a required input optional)",
        _pillar,
    ),
    Detector(
        "effective_duration_alm:when",
        "says_pyvar_revalues_the_inputs",
        "says pyvar re-values the three present values, which the caller supplies",
        "pv_base, pv_up, pv_down are required inputs; the function only combines them",
        "recorded: results 9.10, 9.14, 9.16. The catalogue summary itself says 'from re-valued PVs'",
        lambda text, case: _hits(text, lambda s: bool(_REVALUE_AGENT.search(s))),
    ),
    Detector(
        "fx_forward_pricer:when",
        "notional_affects_forward_or_gives_value",
        "lets notional affect the forward, or says setting it gives a value",
        "F = S e^{(rd-rf)tau} has no notional; notional scales the MtM, which exists only with contracted_forward",
        "recorded: results 9.10, 9.14, 9.16",
        _fx_forward,
    ),
    Detector(
        "cva_sensitivity_cva_greeks:when",
        "unsure_about_a_parameter_or_epe_as_peak",
        "says it is unclear what a parameter does (spread_bump is one), or describes EPE as a peak",
        "spread_bump is a parameter; the sibling listing says EPE is a time-weighted average",
        "recorded: results section 4 item 5 (the parameter claim); the EPE-as-peak sentence is a hypothesis",
        _cva,
    ),
    Detector(
        "conduct_risk_metric:compare:model_risk_assessment",
        "conduct_direction_averaged_or_validation_direction",
        "reverses the conduct index (higher = worse), averages its two parts, or says better validation raises risk",
        "Index = min(CPK,50) + min(500 RR,50), higher = worse; R = I x (1 - V)",
        "hypothesis: the repository records only that Opus flagged this case on 2 of 4 draws",
        _conduct_vs_model_risk,
    ),
    Detector(
        "black_scholes_european_option:when",
        "tree_sibling_given_american_or_path_dependent_payoffs",
        "says a tree sibling handles American or path-dependent payoffs",
        "the listings say only 'Cox-Ross-Rubinstein binomial tree option price' and 'Boyle trinomial tree option price'",
        "recorded: results section 6 (calibration run 3)",
        _black_scholes,
    ),
    Detector(
        "retail_deposit_runoff_rate:explain",
        "says_no_rate_values_are_given",
        "says the documentation gives no run-off rate values",
        "the description gives stable 5% and less-stable 10%; runoff_rates is a required input",
        "recorded: results 9.12 (a false claim that the documentation gives no rate values); 9.10",
        _retail,
    ),
    Detector(
        "esg_score_integration:when",
        "floor_without_covariance_or_maximises_esg",
        "says min_esg_score alone triggers an optimisation, or that it maximises the ESG score",
        "the optimisation runs only when both min_esg_score and cov_matrix are supplied; it minimises variance",
        "hypothesis: the repository records only that Opus flagged this case on 3 of 4 draws",
        _esg,
    ),
]
BY_CASE = {d.case_id: d for d in DETECTORS}
PERSISTENT_IDS = [d.case_id for d in DETECTORS]


def detect(case: dict[str, Any], text: str) -> list[dict[str, Any]]:
    """The detector findings for one answer (empty when the case has no detector or none fires)."""
    detector = BY_CASE.get(case["id"])
    if detector is None or not text.strip():
        return []
    found = detector.find(text, case)
    return [{"detector": detector.key, "sentence": s} for s in found]


def summarise_run(cases: dict[str, dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per persistent case: answers examined, answers where the detector fired (no answer text)."""
    out: dict[str, Any] = {}
    for detector in DETECTORS:
        group = [r for r in rows if r["case_id"] == detector.case_id and r["status"] == "ok"]
        fired = sum(1 for r in group if detect(cases[detector.case_id], r["text"]))
        out[detector.case_id] = {
            "detector": detector.key,
            "evidence": detector.evidence.split(":")[0],
            "answers": len(group),
            "claim_made": fired,
        }
    out["total"] = {
        "answers": sum(v["answers"] for v in out.values()),
        "claim_made": sum(v["claim_made"] for v in out.values()),
    }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--run", required=True, type=Path, action="append", help="a run directory")
    parser.add_argument("--out", type=Path, default=None, help="write the counts here as JSON")
    args = parser.parse_args()
    cases = {c["id"]: c for c in map(json.loads, args.cases.read_text().splitlines()) if c}
    missing = [i for i in PERSISTENT_IDS if i not in cases]
    if missing:
        parser.error(f"cases file lacks the persistent cases: {missing}")
    report: dict[str, Any] = {}
    for run in args.run:
        rows = [json.loads(x) for x in (run / "results.jsonl").read_text().splitlines() if x]
        report[str(run)] = summarise_run(cases, rows)
    text = json.dumps(report, indent=2)
    if args.out:
        args.out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
