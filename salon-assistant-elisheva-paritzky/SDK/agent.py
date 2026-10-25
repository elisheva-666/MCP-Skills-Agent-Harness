"""The SDK-version agent: Claude Code runs the harness, we only configure it."""
import time
from datetime import date
from pathlib import Path

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient,
                              ResultMessage, ToolUseBlock)

from shared import config
from shared.prompts import RULES
from shared.tools import SalonTools

from SDK.tools import Recorder, build_server

WORKSPACE = Path(__file__).resolve().parent / "workspace"


class SalonAgentSDK:
    def __init__(self, state_dir: Path, client_id: str, today: date | None = None):
        self.salon = SalonTools(state_dir, client_id, today=today or date.today())
        self.rec = Recorder()
        self.server, self.allowed, _ = build_server(self.salon, self.rec)
        self.session_id = None  # set by the first turn, then resumed
        self.session_cost = 0.0  # total_cost_usd is cumulative over a resumed session

        # Project memory: Claude Code loads CLAUDE.md from cwd when setting_sources=["project"].
        WORKSPACE.mkdir(exist_ok=True)
        (WORKSPACE / "CLAUDE.md").write_text(  # replaces: memory, context (business facts)
            f"# פרטי העסק\n{self.salon.business_info()}\n", encoding="utf-8")

    def _options(self) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            model=config.MODEL,
            effort=config.EFFORT,
            system_prompt=f"{RULES}\nבתחילת כל שיחה קראי ל-recall_client. today: {self.salon.today}",  # replaces: context
            tools=[],                             # no built-in Claude Code tools (Bash, Read...)
            mcp_servers={"salon": self.server},   # replaces: tools
            allowed_tools=self.allowed,
            strict_mcp_config=True,               # ignore any other MCP config on this machine
            setting_sources=["project"],          # replaces: memory (loads CLAUDE.md)
            cwd=str(WORKSPACE),
            resume=self.session_id,               # replaces: history
            max_turns=10,                         # replaces: loop (safety cap)
        )

    async def ask(self, text: str) -> dict:
        started = time.perf_counter()
        self.rec.calls, self.rec.images = [], []
        reply, result = "", None
        async with ClaudeSDKClient(options=self._options()) as client:
            await client.query(text)                      # replaces: loop
            async for msg in client.receive_response():   # replaces: loop
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, ToolUseBlock):
                            print(f"  [sdk] tool {block.name}({block.input})")
                elif isinstance(msg, ResultMessage):
                    result = msg
                    reply = msg.result or ""
        self.session_id = result.session_id               # replaces: history
        u = result.usage or {}                            # replaces: tokens
        turn_cost = (result.total_cost_usd or 0) - self.session_cost  # replaces: tokens
        self.session_cost = result.total_cost_usd or 0    # replaces: tokens
        return {
            "reply": reply,
            "tools": list(self.rec.calls),
            "images": list(self.rec.images),
            "input": u.get("input_tokens", 0),                     # replaces: tokens
            "cache_read": u.get("cache_read_input_tokens", 0),     # replaces: tokens
            "cache_write": u.get("cache_creation_input_tokens", 0),  # replaces: tokens
            "output": u.get("output_tokens", 0),                   # replaces: tokens
            "model_calls": result.num_turns,                       # replaces: tokens
            "cost_usd": round(turn_cost, 6),                       # replaces: tokens
            "seconds": round(time.perf_counter() - started, 2),
            "session_id": result.session_id,
        }
