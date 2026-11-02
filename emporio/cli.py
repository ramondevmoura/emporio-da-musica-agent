"""Terminal chat, mainly for development: `python -m emporio.cli [--debug] [--session ID]`."""

from __future__ import annotations

import argparse
import json
import uuid

from emporio.agent import Agent, visible_messages
from emporio.memory import ConversationStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat with the Empório da Música assistant")
    parser.add_argument("--debug", action="store_true", help="show tool calls and token usage")
    parser.add_argument("--session", help="resume a saved conversation")
    args = parser.parse_args()

    store = ConversationStore()
    session = args.session or f"cli-{uuid.uuid4().hex[:8]}"
    history = store.load(session)
    agent = Agent()

    print(f"Empório da Música - sessão {session} (Ctrl+C para sair)\n")
    for role, text in visible_messages(history):
        print(f"{'Você' if role == 'user' else 'Lia'}: {text}\n")

    while True:
        try:
            message = input("Você: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if not message:
            continue
        result = agent.respond(history, message)
        if args.debug:
            for ev in result.tool_events:
                print(f"  [tool] {ev.name}({json.dumps(ev.arguments, ensure_ascii=False)})")
            print(f"  [usage] {result.usage}")
        print(f"\nLia: {result.reply}\n")
        history += result.new_items
        store.append(session, result.new_items)


if __name__ == "__main__":
    main()
