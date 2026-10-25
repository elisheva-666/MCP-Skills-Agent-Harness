"""Run the scenario on the SDK version.

    python SDK/main.py --scenario scenario.json --out results/sdk.json
Runs on your Claude Code login. ANTHROPIC_API_KEY is removed so billing stays on the login.
"""
import argparse
import asyncio
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from shared import scenario as sc  # noqa: E402
from SDK.agent import SalonAgentSDK  # noqa: E402


async def run(args) -> None:
    os.environ.pop("ANTHROPIC_API_KEY", None)
    scen = sc.load(args.scenario)
    state = sc.clean_state("sdk")
    today = date.fromisoformat(scen["today"])
    turns = []
    for session in scen["sessions"]:
        print(f"\n=== session {session['id']}: new agent instance, state loaded from disk ===")
        agent = SalonAgentSDK(state, scen["client_id"], today=today)
        for i, text in enumerate(session["turns"], 1):
            print(f"\n> {text}")
            rec = await agent.ask(text)
            print(f"< {rec['reply']}")
            turns.append({"session": session["id"], "turn": i, "user": text, **rec})

    checks = sc.run_checks(scen, state, turns)
    for c in checks:
        print(f"{'PASS' if c['passed'] else 'FAIL'}  {c['id']}")
    sc.write_results(args.out, "sdk", turns, checks, sc.loc_sdk())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="scenario.json")
    ap.add_argument("--out", default="results/sdk.json")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
