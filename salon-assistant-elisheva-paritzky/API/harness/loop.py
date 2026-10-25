"""The agent loop: call the model, run the tools it asks for, repeat until it stops asking.

One user turn can take several model calls:
    call 1 -> stop_reason "tool_use"  -> run tools, send ALL results back in ONE user message
    call 2 -> stop_reason "tool_use"  -> same again
    call 3 -> stop_reason "end_turn"  -> done, the text is the answer
"""
from dataclasses import dataclass, field

from shared import config

from API.harness.caching import with_breakpoints
from API.harness.tools import TOOL_SCHEMAS, ToolBox
from API.harness.trace import log

SRC = "loop.py"
MAX_MODEL_CALLS = 8  # safety net against a model that never stops calling tools


@dataclass
class TurnResult:
    text: str
    responses: list = field(default_factory=list)  # every API response, for tokens.py
    tools_called: list = field(default_factory=list)
    images: list = field(default_factory=list)


def run_turn(client, toolbox: ToolBox, system: list[dict], messages: list) -> TurnResult:
    """Run one user turn. `messages` already ends with the new user message and is
    extended in place with every assistant/tool_result message this turn produces."""
    toolbox.start_turn()
    responses = []

    for call in range(1, MAX_MODEL_CALLS + 1):
        log(SRC, f"model call {call}: sending {len(messages)} messages")
        cached_system, cached_messages = with_breakpoints(system, messages)
        response = client.beta.messages.create(
            model=config.MODEL,
            max_tokens=16000,
            output_config={"effort": config.EFFORT},
            # If a safety classifier declines, the API retries on a fallback model in the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=cached_system,
            tools=TOOL_SCHEMAS,
            messages=cached_messages,
        )
        responses.append(response)

        # Keep the assistant message exactly as returned (thinking blocks included),
        # as plain dicts so history.py can save it to disk.
        messages.append({"role": "assistant", "content": [b.to_dict() for b in response.content]})
        log(SRC, f"stop_reason={response.stop_reason}")

        if response.stop_reason != "tool_use":
            break

        tool_uses = [b for b in messages[-1]["content"] if b["type"] == "tool_use"]
        results = [toolbox.run(b) for b in tool_uses]
        messages.append({"role": "user", "content": results})  # all results in ONE message
    else:
        log(SRC, f"stopped after {MAX_MODEL_CALLS} model calls")

    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if response.stop_reason == "refusal":
        text = text or "מצטערת, אין לי אפשרות לעזור בזה. אפשר לפנות אלינו בטלפון."
    elif response.stop_reason == "max_tokens":
        log(SRC, "WARNING: answer cut off by max_tokens")

    return TurnResult(text=text, responses=responses,
                      tools_called=list(toolbox.calls), images=list(toolbox.shown_images))
