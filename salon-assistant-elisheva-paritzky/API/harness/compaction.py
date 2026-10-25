"""Context-window management: past a threshold, replace the conversation with a summary.

Checked before each turn using the prompt size of the previous call. When it is over
the threshold, one extra model call summarizes the whole conversation, history.py
records the summary (append-only), and the live messages become just that summary.
Long-term facts are safe either way: they live in memory.py, not in the conversation.
"""
from shared import config

from API.harness.history import History
from API.harness.trace import log

SRC = "compaction.py"
THRESHOLD_TOKENS = 40_000  # far below the 1M window: a salon chat never needs more

PROMPT = ("סכמי את השיחה עד כה ב-5 שורות לכל היותר: מה הלקוחה ביקשה, מה הוחלט, "
          "אילו תורים נקבעו ומה עוד פתוח. בלי פתיח.")


def maybe_compact(client, messages: list[dict], last_context_tokens: int, history: History,
                  threshold: int = THRESHOLD_TOKENS):
    """Return (messages, summary_response or None)."""
    if last_context_tokens <= threshold or not messages:
        return messages, None
    log(SRC, f"context {last_context_tokens} > {threshold} tokens: summarizing {len(messages)} messages")
    response = client.messages.create(
        model=config.MODEL,
        max_tokens=2000,
        output_config={"effort": "low"},
        messages=messages + [{"role": "user", "content": PROMPT}],
    )
    summary = "".join(b.text for b in response.content if b.type == "text").strip()
    history.append_compaction(summary)
    log(SRC, f"replaced with a {len(summary)}-char summary")
    return [{"role": "user", "content": f"[סיכום השיחה עד כה]\n{summary}"}], response
