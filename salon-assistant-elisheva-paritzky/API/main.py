"""Run the scenario on the API version.

    python API/main.py --scenario scenario.json --out results/api.json
Needs ANTHROPIC_API_KEY in the terminal environment (never in code).
"""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import anthropic  # noqa: E402

from shared import scenario as sc  # noqa: E402
from API.agent import SalonAgent  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="scenario.json")
    ap.add_argument("--out", default="results/api.json")
    args = ap.parse_args()

    scen = sc.load(args.scenario)
    state = sc.clean_state("api")
    today = date.fromisoformat(scen["today"])
    turns = []
    for session in scen["sessions"]:
        print(f"\n=== session {session['id']}: new agent instance, state loaded from disk ===")
        agent = SalonAgent(anthropic.Anthropic(), state, scen["client_id"], session["id"], today=today)
        for i, text in enumerate(session["turns"], 1):
            print(f"\n> {text}")
            rec = agent.ask(text)
            print(f"< {rec['reply']}")
            turns.append({"session": session["id"], "turn": i, "user": text, **rec})

    checks = sc.run_checks(scen, state, turns)
    for c in checks:
        print(f"{'PASS' if c['passed'] else 'FAIL'}  {c['id']}")
    sc.write_results(args.out, "api", turns, checks, sc.loc_api())


if __name__ == "__main__":
    main()
