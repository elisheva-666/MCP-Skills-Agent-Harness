"""Prompt caching: mark where the reusable prefix ends.

The API caches a prefix (tools -> system -> messages) up to each cache_control marker.
A later call that starts with the same bytes reads it at ~5% of the input price.
Two breakpoints:
  1. end of the system prompt: tools + system never change, reused by every call and session.
  2. end of the last message: the conversation so far, reused by the next call in this turn
     (after a tool round) and by the next turn.
"""
import copy

from API.harness.trace import log

SRC = "caching.py"
MARK = {"type": "ephemeral"}


def with_breakpoints(system: list[dict], messages: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return copies with cache_control added; the stored history stays unmarked."""
    system = copy.deepcopy(system)
    system[-1]["cache_control"] = MARK

    messages = copy.deepcopy(messages)
    last = messages[-1]
    if isinstance(last["content"], str):
        last["content"] = [{"type": "text", "text": last["content"]}]
    last["content"][-1]["cache_control"] = MARK
    log(SRC, f"breakpoints: system + message #{len(messages)}")
    return system, messages
