"""What the model sees on each turn.

Stable part (system prompt): role, rules, business info. Identical on every call,
so it is cached (see caching.py). Nothing that changes may go here.

Per-turn part (a short block in front of the user's message): today's date and the
client's profile from memory.py.

Deliberately NOT included: the service catalog, gallery and calendar. The model pulls
just the slice it needs with tools, so a question about courses never pays for the gallery.
"""
from datetime import date

from shared.prompts import RULES
from shared.tools import SalonTools

from API.harness.trace import log

SRC = "context.py"


def system_prompt(salon: SalonTools) -> list[dict]:
    text = f"{RULES}\n\nפרטי העסק:\n{salon.business_info()}"
    log(SRC, f"system prompt: {len(text)} chars (stable, cacheable)")
    return [{"type": "text", "text": text}]


def user_message(user_text: str, profile: str, today: date) -> dict:
    block = f"<context>\ntoday: {today.isoformat()} ({today.strftime('%A')})\nclient:\n{profile}\n</context>"
    log(SRC, f"per-turn context: {len(block)} chars (date + client profile)")
    return {"role": "user", "content": [{"type": "text", "text": block}, {"type": "text", "text": user_text}]}
