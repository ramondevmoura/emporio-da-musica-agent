"""Run the eval scenarios against the real model.

    python -m evals.run_evals                 # all scenarios
    python -m evals.run_evals -k price        # scenarios whose id contains "price"
    python -m evals.run_evals --model gpt-5.4 # compare another model

Writes a JSON report (with full transcripts and tool calls) to evals/results/.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from emporio.agent import Agent
from evals.scenarios import DEFAULT_MAX_LINES, SCENARIOS

RESULTS_DIR = Path(__file__).parent / "results"


def normalize(text: str) -> str:
    """Lowercase, no accents, punctuation -> spaces (keeps '%')."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9%]+", " ", text).strip()


def check(scenario: dict, reply: str, tools_called: list[str]) -> list[str]:
    failures = []
    text = f" {normalize(reply)} "
    for tool in scenario.get("expect_tools", []):
        if tool not in tools_called:
            failures.append(f"expected tool {tool}")
    for tool in scenario.get("forbid_tools", []):
        if tool in tools_called:
            failures.append(f"forbidden tool {tool}")
    for group in scenario.get("include_any", []):
        if not any(re.search(p, text) for p in group):
            failures.append(f"missing one of {group}")
    for pattern in scenario.get("exclude", []):
        if re.search(pattern, text):
            failures.append(f"should not contain {pattern!r}")
    lines = [line for line in reply.splitlines() if line.strip()]
    if len(lines) > scenario.get("max_lines", DEFAULT_MAX_LINES):
        failures.append(f"too long: {len(lines)} lines")
    return failures


def run_scenario(agent: Agent, scenario: dict) -> dict:
    history: list[dict] = []
    transcript, tools_called, usage = [], [], {"input_tokens": 0, "output_tokens": 0}
    start = time.time()
    reply = ""
    for message in scenario["turns"]:
        result = agent.respond(history, message)
        history += result.new_items
        reply = result.reply
        tools_called += [e.name for e in result.tool_events]
        for k in usage:
            usage[k] += result.usage.get(k, 0)
        transcript.append(
            {
                "user": message,
                "assistant": reply,
                "tools": [{"name": e.name, "args": e.arguments} for e in result.tool_events],
            }
        )
    failures = check(scenario, reply, tools_called)
    return {
        "id": scenario["id"],
        "passed": not failures,
        "failures": failures,
        "seconds": round(time.time() - start, 1),
        "usage": usage,
        "transcript": transcript,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-k", help="only run scenarios whose id contains this text")
    parser.add_argument("--model", help="override OPENAI_MODEL")
    args = parser.parse_args()

    agent = Agent(model=args.model)
    scenarios = [s for s in SCENARIOS if not args.k or args.k in s["id"]]
    results = []
    for s in scenarios:
        r = run_scenario(agent, s)
        results.append(r)
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"[{mark}] {r['id']:40} {r['seconds']:5}s  {'; '.join(r['failures'])}")

    passed = sum(r["passed"] for r in results)
    print(f"\n{passed}/{len(results)} passed with {agent.model}")
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{agent.model}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report: {out}")


if __name__ == "__main__":
    main()
