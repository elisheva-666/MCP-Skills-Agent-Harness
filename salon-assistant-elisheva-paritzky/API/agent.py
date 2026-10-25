"""The API-version agent: wires the harness files together for one client and one session."""
import time
from datetime import date
from pathlib import Path

from shared.tools import SalonTools

from API.harness import compaction, context, memory, tokens
from API.harness.history import History
from API.harness.loop import run_turn
from API.harness.tools import ToolBox


class SalonAgent:
    def __init__(self, client, state_dir: Path, client_id: str, session_id: str,
                 today: date | None = None, http_get=None):
        kwargs = {"http_get": http_get} if http_get else {}
        self.client = client
        self.today = today or date.today()
        self.salon = SalonTools(state_dir, client_id, today=self.today, **kwargs)
        self.toolbox = ToolBox(self.salon)
        self.history = History(state_dir, session_id)
        self.messages = self.history.load()          # resume from disk if the session exists
        self.system = context.system_prompt(self.salon)
        self.last_context_tokens = 0

    def ask(self, text: str) -> dict:
        started = time.perf_counter()
        extra_responses = []

        self.messages, summary_resp = compaction.maybe_compact(
            self.client, self.messages, self.last_context_tokens, self.history)
        if summary_resp:
            extra_responses.append(summary_resp)

        profile = memory.client_profile(self.salon)
        self.messages.append(context.user_message(text, profile, self.today))
        first_new = len(self.messages) - 1

        result = run_turn(self.client, self.toolbox, self.system, self.messages)

        for msg in self.messages[first_new:]:
            self.history.append(msg)
        self.last_context_tokens = tokens.context_size(result.responses[-1])

        usage = tokens.turn_usage(extra_responses + result.responses)
        return {
            "reply": result.text,
            "tools": result.tools_called,
            "images": result.images,
            **usage,
            "seconds": round(time.perf_counter() - started, 2),
        }
