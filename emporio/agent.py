"""The agent loop: OpenAI Responses API + function calling, no framework.

One turn = send history + user message -> run any requested tools -> send the results back,
until the model answers with text (or the tool-call budget runs out).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from emporio import config
from emporio.data import StoreData, get_store_data
from emporio.fallback import fallback_message
from emporio.prompts import build_system_prompt
from emporio.tools import build_tool_schemas, run_tool

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6
REQUEST_TIMEOUT_S = 25  # per API call; a chat customer should not wait longer than this
MAX_RETRIES = 1  # the SDK retries 429/5xx/connection errors once, with backoff
CIRCUIT_OPEN_S = 60  # after a failure, skip the API for a minute instead of timing out again


class LLMUnavailable(Exception):
    """The model could not produce an answer (outage, timeout, empty output...)."""


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
    degraded: bool = False  # True when the reply is the deterministic fallback


class Agent:
    def __init__(
        self,
        client: OpenAI | None = None,
        data: StoreData | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
    ):
        self.client = client or OpenAI(
            api_key=config.OPENAI_API_KEY or None,
            timeout=REQUEST_TIMEOUT_S,
            max_retries=MAX_RETRIES,
        )
        self.data = data or get_store_data()
        self.model = model or config.OPENAI_MODEL
        self.reasoning_effort = (
            config.OPENAI_REASONING_EFFORT if reasoning_effort is None else reasoning_effort
        )
        self.instructions = build_system_prompt()
        self.tools = build_tool_schemas(self.data)
        self._circuit_open_until = 0.0

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
        """Answer one customer message. Never raises: on any LLM failure it returns the
        deterministic fallback (store contacts, hours, open/closed now)."""
        user_item = {"role": "user", "content": user_message}
        events: list[ToolEvent] = []
        usage = {"input_tokens": 0, "cached_tokens": 0, "output_tokens": 0}

        if time.monotonic() < self._circuit_open_until:
            log.warning("LLM circuit open, answering with the fallback")
            return self._fallback(user_item, events, usage)
        try:
            reply, new_items = self._run_loop(history, user_item, events, usage)
        except Exception:
            log.exception("LLM unavailable, answering with the fallback")
            self._circuit_open_until = time.monotonic() + CIRCUIT_OPEN_S
            return self._fallback(user_item, events, usage)
        return TurnResult(reply, new_items, events, usage)

    def _fallback(self, user_item: dict, events: list[ToolEvent], usage: dict) -> TurnResult:
        reply = fallback_message()
        # Keep only the user message and the fallback (no half-finished tool calls), so the
        # conversation stays valid when the API comes back.
        items = [user_item, {"role": "assistant", "content": reply}]
        return TurnResult(reply, items, events, usage, degraded=True)

    def _run_loop(
        self, history: list[dict], user_item: dict, events: list[ToolEvent], usage: dict
    ) -> tuple[str, list[dict]]:
        new_items: list[dict] = [user_item]
        for _ in range(MAX_TOOL_ROUNDS):
            response = self._create(history + new_items)

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
                reply = response.output_text.strip()
                if not reply:
                    raise LLMUnavailable("empty answer")
                return reply, new_items

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
        raise LLMUnavailable("tool-call budget exhausted")


def visible_messages(items: list[dict]) -> list[tuple[str, str]]:
    """Extract (role, text) pairs for display, skipping tool calls and reasoning items."""
    out = []
    for item in items:
        if item.get("role") in ("user", "assistant") and isinstance(item.get("content"), str):
            out.append((item["role"], item["content"]))  # user messages and fallback replies
        elif item.get("type") == "message" and item.get("role") == "assistant":
            text = "".join(
                c.get("text", "") for c in item.get("content", []) if c.get("type") == "output_text"
            )
            if text.strip():
                out.append(("assistant", text.strip()))
    return out
