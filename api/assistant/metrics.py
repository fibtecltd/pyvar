"""
api/assistant/metrics.py — Prometheus metrics for the typed-question gateway

Reasoning:
- Registered in the default registry that prometheus-fastapi-instrumentator already exposes at /metrics, like
  observability/setup.py's custom histograms. Every label has a small fixed set of values (outcomes come from
  assistant/guardrails.py, tiers from the config, refusal reasons from routes.py), so cardinality is bounded.
- Nothing here ever carries visitor text: only counts, dollars and seconds.
- `budget_used_ratio` is set every time the gate is read, so an alert can fire at 80% of the day's cap before
  the circuit breaker opens at 100%.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

ANSWERS = Counter(
    "pyvar_assistant_answers",
    "Typed questions answered, by source (live|static), guardrail outcome, caller tier and model tier",
    ["source", "outcome", "tier", "model_tier"],
)
REFUSED = Counter(
    "pyvar_assistant_refused",
    "Typed questions refused before any model call (disabled|budget|unavailable|busy|quota)",
    ["reason", "tier"],
)
COST_USD = Counter(
    "pyvar_assistant_cost_usd",
    "Model dollars spent answering typed questions, by model tier",
    ["model_tier"],
)
ANSWER_SECONDS = Histogram(
    "pyvar_assistant_answer_seconds",
    "Wall-clock seconds to answer one typed question (model calls, tools and checks)",
    buckets=[0.5, 1.0, 2.0, 4.0, 8.0, 15.0, 30.0, 60.0],
)
INFLIGHT = Gauge("pyvar_assistant_inflight", "Typed questions being answered on this API task")
BUDGET_USED_RATIO = Gauge(
    "pyvar_assistant_budget_used_ratio",
    "Today's recorded model spend divided by assistant_daily_budget_usd (read before each question)",
)
SPEND_NOT_RECORDED = Counter(
    "pyvar_assistant_spend_not_recorded",
    "Answers whose cost could not be added to the day's spend (Redis write failed): the cap undercounts",
)
UNEXPECTED_ERRORS = Counter(
    "pyvar_assistant_unexpected_errors",
    "Typed questions that ended in an unexpected exception (a bug, not a model problem)",
)
