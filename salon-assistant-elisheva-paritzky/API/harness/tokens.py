"""Token usage and cost per turn.

Every response carries usage: input_tokens (uncached), cache_read_input_tokens,
cache_creation_input_tokens (cache write) and output_tokens. A turn = the sum over
all its model calls.
"""
from API.harness.trace import log

SRC = "tokens.py"

# claude-opus-5-5, USD per million tokens
PRICE = {"input": 4.00, "cache_write": 5.00, "cache_read": 0.20, "output": 20.00}


def usage_of(response) -> dict:
    u = response.usage
    return {
        "input": u.input_tokens or 0,
        "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "output": u.output_tokens or 0,
    }


def cost(usage: dict) -> float:
    return sum(usage[k] * PRICE[k] for k in PRICE) / 1_000_000


def turn_usage(responses: list) -> dict:
    total = {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0}
    for r in responses:
        for k, v in usage_of(r).items():
            total[k] += v
    total["model_calls"] = len(responses)
    total["cost_usd"] = round(cost(total), 6)
    prompt = total["input"] + total["cache_read"] + total["cache_write"]
    total["cache_hit_pct"] = round(100 * total["cache_read"] / prompt, 1) if prompt else 0.0
    log(SRC, f"in={total['input']} cache_read={total['cache_read']} cache_write={total['cache_write']} "
             f"out={total['output']} calls={len(responses)} ${total['cost_usd']:.4f} ({total['cache_hit_pct']}% cached)")
    return total


def context_size(response) -> int:
    """How big the prompt was on this call: what compaction.py compares to its threshold."""
    u = usage_of(response)
    return u["input"] + u["cache_read"] + u["cache_write"]
