"""Token prices and cost arithmetic for the assistant eval.

Reasoning:
- Cost is computed from the `usage` block the API returns for each call, at the rate of the model that
  served it, never from a flat assumed rate (an eval that estimates tokens from string length can reverse a
  cost comparison).
- Rates are per million tokens for prompts of 100K tokens or fewer, from the Claude API reference bundled
  with Claude Code (model table cached 2026-10-06). Cache reads are a multiple of the input rate, 5-minute
  cache writes 1.25x. Verify against Anthropic's live pricing page before relying on them for a budget.
- Every prompt in this eval is far below 100K tokens; a larger one raises, because Haiku 5.5 switches to a
  dearer rate card above that and silently pricing it at the low rate would under-report cost.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

PROMPT_RATE_CARD_LIMIT = 100_000


@dataclass(frozen=True)
class Price:
    """Dollars per million tokens, for prompts of 100K tokens or fewer."""

    input: float
    output: float
    cache_read_multiplier: float
    cache_write_multiplier: float = 1.25  # 5-minute TTL


PRICES: dict[str, Price] = {
    "claude-haiku-5-5": Price(input=0.10, output=0.50, cache_read_multiplier=0.10),
    "claude-sonnet-5-5": Price(input=2.00, output=10.00, cache_read_multiplier=0.10),
    "claude-opus-5-5": Price(input=4.00, output=20.00, cache_read_multiplier=0.05),
}


def usage_cost(model: str, usage: Mapping[str, int]) -> float:
    """Dollar cost of one API call.

    Args:
        model: the model id that served the call (a key of PRICES).
        usage: the response's usage counts: input_tokens, output_tokens, cache_read_input_tokens,
            cache_creation_input_tokens (missing keys count as 0). Output tokens include thinking.

    Returns:
        Cost in US dollars.

    Raises:
        KeyError: if the model has no price entry.
        ValueError: if the prompt is long enough to move to the dearer rate card.
    """
    price = PRICES[model]
    fresh = int(usage.get("input_tokens", 0) or 0)
    read = int(usage.get("cache_read_input_tokens", 0) or 0)
    write = int(usage.get("cache_creation_input_tokens", 0) or 0)
    out = int(usage.get("output_tokens", 0) or 0)
    if fresh + read + write > PROMPT_RATE_CARD_LIMIT:
        raise ValueError(
            f"prompt over {PROMPT_RATE_CARD_LIMIT} tokens: this price table does not apply"
        )
    per_token = 1e-6
    return (
        fresh * price.input
        + read * price.input * price.cache_read_multiplier
        + write * price.input * price.cache_write_multiplier
        + out * price.output
    ) * per_token
