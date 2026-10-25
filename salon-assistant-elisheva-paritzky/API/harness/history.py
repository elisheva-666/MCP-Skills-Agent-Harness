"""Conversation history on disk, append-only (one JSON record per line).

Records are never rewritten. Compaction does not delete old lines; it appends a
"compaction" record, and load() rebuilds the live conversation from the last one.
"""
import json
from pathlib import Path

from API.harness.trace import log

SRC = "history.py"


class History:
    def __init__(self, state_dir: Path, session_id: str):
        self.path = Path(state_dir) / "history" / f"{session_id}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, message: dict) -> None:
        self._write({"type": "message", "message": message})

    def append_compaction(self, summary: str) -> None:
        self._write({"type": "compaction", "summary": summary})

    def _write(self, record: dict) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def load(self) -> list[dict]:
        """Live messages: everything after the last compaction, led by its summary."""
        if not self.path.exists():
            log(SRC, f"new session file {self.path.name}")
            return []
        messages: list[dict] = []
        records = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]
        for rec in records:
            if rec["type"] == "compaction":
                messages = [{"role": "user", "content": f"[סיכום השיחה עד כה]\n{rec['summary']}"}]
            else:
                messages.append(rec["message"])
        log(SRC, f"loaded {len(messages)} messages from {self.path.name} ({len(records)} records)")
        return messages
