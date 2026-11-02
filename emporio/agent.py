"""The agent loop: OpenAI Responses API + function calling, no framework.

One turn = send history + user message -> run any requested tools -> send the results back,
until the model answers with text (or the tool-call budget runs out).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from openai import APIError, OpenAI

from emporio import config
from emporio.data import StoreData, get_store_data
from emporio.prompts import build_system_prompt
from emporio.tools import build_tool_schemas, run_tool

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6
FALLBACK_REPLY = (
    "Desculpe, tive um probleminha técnico agora. 😕 Pode tentar de novo? Se preferir, fale "
    "com a nossa equipe no WhatsApp (67) 3321-4500."
)


@dataclass
class ToolEvent:
    name: str
    arguments: dict
    result: dict


@dataclass
class TurnResult:
    reply: str
    new_items: list[dict]  # items to append to the conversation history
    tool_events: list[ToolEvent] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)


class Agent:
    def __init__(
        self,
        client: OpenAI | None = None,
        data: StoreData | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
    ):
        self.client = client or OpenAI(api_key=config.OPENAI_API_KEY or None)
        self.data = data or get_store_data()
        self.model = model or config.OPENAI_MODEL
        self.reasoning_effort = (
            config.OPENAI_REASONING_EFFORT if reasoning_effort is None else reasoning_effort
        )
        self.instructions = build_system_prompt()
        self.tools = build_tool_schemas(self.data)

    def _create(self, input_items: list[dict]):
        kwargs: dict[str, Any] = {
            "model": self.model,
            "instructions": self.instructions,
            "tools": self.tools,
            "input": input_items,
            "prompt_cache_key": "emporio-agent-v1",
            "max_output_tokens": 2000,
        }
        if self.reasoning_effort:
            kwargs["reasoning"] = {"effort": self.reasoning_effort}
        return self.client.responses.create(**kwargs)

    def respond(self, history: list[dict], user_message: str) -> TurnResult:
        new_items: list[dict] = [{"role": "user", "content": user_message}]
        events: list[ToolEvent] = []
        usage = {"input_tokens": 0, "cached_tokens": 0, "output_tokens": 0}

        for _ in range(MAX_TOOL_ROUNDS):
            try:
                response = self._create(history + new_items)
            except APIError as exc:
                log.exception("OpenAI API error")
                return TurnResult(FALLBACK_REPLY, [], events, {"error": str(exc)})  # type: ignore[dict-item]

            if response.usage:
                usage["input_tokens"] += response.usage.input_tokens
                usage["output_tokens"] += response.usage.output_tokens
                details = response.usage.input_tokens_details
                usage["cached_tokens"] += getattr(details, "cached_tokens", 0) or 0

            calls = [item for item in response.output if item.type == "function_call"]
            new_items += [
                item.model_dump(exclude_none=True, mode="json") for item in response.output
            ]
            if not calls:
                reply = response.output_text.strip() or FALLBACK_REPLY
                return TurnResult(reply, new_items, events, usage)

            for call in calls:
                try:
                    args = json.loads(call.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = run_tool(self.data, call.name, args)
                events.append(ToolEvent(call.name, args, result))
                log.info("tool %s(%s)", call.name, args)
                new_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(result, ensure_ascii=False),
                    }
                )

        return TurnResult(FALLBACK_REPLY, new_items, events, usage)


def visible_messages(items: list[dict]) -> list[tuple[str, str]]:
    """Extract (role, text) pairs for display, skipping tool calls and reasoning items."""
    out = []
    for item in items:
        if item.get("role") == "user" and isinstance(item.get("content"), str):
            out.append(("user", item["content"]))
        elif item.get("type") == "message" and item.get("role") == "assistant":
            text = "".join(
                c.get("text", "") for c in item.get("content", []) if c.get("type") == "output_text"
            )
            if text.strip():
                out.append(("assistant", text.strip()))
    return out
