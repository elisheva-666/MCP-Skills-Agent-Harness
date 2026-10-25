"""Long-term memory: facts about a client that survive between sessions.

Where: state/api/memory.json, keyed by client_id (written by the remember_client_fact tool).
How it is retrieved: by the harness, not the model. At the start of every turn the
current client's profile (current values only, no history) is read and handed to
context.py. It is a few lines, so it is cheaper to always include it than to make
the model spend a tool call on fetching it.
"""
from shared.tools import SalonTools

from API.harness.trace import log

SRC = "memory.py"


def client_profile(salon: SalonTools) -> str:
    profile = salon.recall_client()
    log(SRC, f"profile for {salon.client_id}: {profile.replace(chr(10), ' / ')}")
    return profile
