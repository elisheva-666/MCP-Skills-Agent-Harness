"""Scenario plumbing shared by both versions: load, checks, totals, line counts, output file.

Most checks read the saved state (memory.json, bookings.json), not the reply text:
a polite answer that forgot to save anything must fail.
"""
import json
import re
import shutil
from pathlib import Path

from shared import config
from shared.store import read_json

USAGE_KEYS = ["input", "cache_read", "cache_write", "output", "model_calls", "cost_usd", "seconds"]


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def clean_state(version: str) -> Path:
    """Every run starts from an empty state folder."""
    shutil.rmtree(config.STATE_ROOT / version, ignore_errors=True)
    return config.state_dir(version)


def run_checks(scenario: dict, state_dir: Path, turns: list[dict]) -> list[dict]:
    cid = scenario["client_id"]
    facts = read_json(state_dir / "memory.json", {}).get(cid, {})
    bookings = [b for b in read_json(state_dir / "bookings.json", []) if b["client_id"] == cid]
    results = []
    for c in scenario["checks"]:
        t = c["type"]
        if t == "memory_contains":
            value = facts.get(c["key"], {}).get("value", "")
            passed, detail = any(w in value for w in c["any"]), value
        elif t == "memory_previous_contains":
            prev = facts.get(c["key"], {}).get("previous", [])
            passed, detail = any(w in p for p in prev for w in c["any"]), prev
        elif t == "booking":
            passed = (len(bookings) == c["count"]
                      and all(b["date"] == c["date"] and b["time"] == c["time"] for b in bookings))
            detail = bookings
        elif t == "tool_called":
            passed = any(c["tool"] in tr["tools"] for tr in turns)
            detail = sum(tr["tools"].count(c["tool"]) for tr in turns)
        elif t == "image_shown":
            shown = [img for tr in turns if tr["session"] == c["session"] for img in tr["images"]]
            passed, detail = c["file"] in shown, shown
        elif t == "reply_contains":
            reply = next(tr["reply"] for tr in turns if tr["session"] == c["session"] and tr["turn"] == c["turn"])
            passed, detail = any(w in reply for w in c["any"]), reply[:120]
        else:
            raise ValueError(f"unknown check type {t}")
        results.append({"id": c["id"], "description": c["description"], "passed": passed, "detail": detail})
    return results


def totals(turns: list[dict]) -> dict:
    tot = {k: round(sum(t[k] for t in turns), 6) for k in USAGE_KEYS}
    prompt = tot["input"] + tot["cache_read"] + tot["cache_write"]
    tot["cache_hit_pct"] = round(100 * tot["cache_read"] / prompt, 1) if prompt else 0.0
    return tot


def _code_lines(path: Path) -> list[str]:
    lines, in_doc = [], False
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if in_doc:
            if s.endswith(('"""', "'''")):
                in_doc = False
            continue
        if s.startswith(('"""', "'''")):
            if not (len(s) > 3 and s.endswith(('"""', "'''"))):
                in_doc = not in_doc
            continue
        if in_doc or not s or s.startswith("#"):
            continue
        lines.append(raw)
    return lines


def loc_api() -> dict:
    harness = config.ROOT / "API" / "harness"
    out = {p.stem: len(_code_lines(p)) for p in sorted(harness.glob("*.py")) if p.stem != "__init__"}
    out["agent+main"] = sum(len(_code_lines(config.ROOT / "API" / f)) for f in ("agent.py", "main.py"))
    out["total"] = sum(out.values())
    return out


def loc_sdk() -> dict:
    """Lines tagged '# replaces: <name>' count toward that harness part."""
    out, total = {}, 0
    for f in ("agent.py", "tools.py", "main.py"):
        for line in _code_lines(config.ROOT / "SDK" / f):
            total += 1
            m = re.search(r"# replaces: ([\w, ]+)", line)
            if m:
                for name in m.group(1).split(","):
                    out[name.strip()] = out.get(name.strip(), 0) + 1
    out["total"] = total
    return out


def write_results(path: str, version: str, turns: list[dict], checks: list[dict], loc: dict) -> None:
    data = {
        "version": version,
        "model": config.MODEL,
        "effort": config.EFFORT,
        "turns": turns,
        "totals": totals(turns),
        "checks_passed": f"{sum(c['passed'] for c in checks)}/{len(checks)}",
        "checks": checks,
        "lines_of_code": loc,
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\nchecks {data['checks_passed']} | ${data['totals']['cost_usd']:.4f} | wrote {path}")
