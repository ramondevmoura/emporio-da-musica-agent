"""The agent must never leave a customer without an answer when the LLM is down."""

from datetime import datetime

import httpx2
import openai

from emporio import agent as agent_module
from emporio.agent import Agent, visible_messages
from emporio.fallback import fallback_message
from emporio.store_hours import TZ
from tests.test_agent import FakeClient, FakeItem, response


class DownClient(FakeClient):
    def _create(self, **kwargs):
        self.calls.append(kwargs)
        raise openai.APIConnectionError(request=httpx2.Request("POST", "https://api.openai.com"))


def test_fallback_message_has_contacts_hours_and_live_status():
    open_msg = fallback_message(datetime(2026, 11, 3, 15, tzinfo=TZ))  # Tuesday 15h
    assert "(67) 3321-4500" in open_msg and "(67) 3341-4444" in open_msg
    assert "Rua 14 de Maio" in open_msg
    assert "aberta, até as 18:00" in open_msg

    closed_msg = fallback_message(datetime(2026, 11, 2, 10, tzinfo=TZ))  # Finados
    assert "fechada (Finados)" in closed_msg
    assert "amanhã às 09:00" in closed_msg


def test_api_outage_returns_fallback_and_keeps_history_valid():
    agent = Agent(client=DownClient([]), model="m", reasoning_effort="")
    result = agent.respond([], "Quanto custa o Takamine GD20?")
    assert result.degraded is True
    assert "(67) 3321-4500" in result.reply
    # history gets the user message + the fallback, shown normally in the chat
    assert visible_messages(result.new_items) == [
        ("user", "Quanto custa o Takamine GD20?"),
        ("assistant", result.reply),
    ]


def test_circuit_breaker_skips_api_then_recovers(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(agent_module.time, "monotonic", lambda: clock[0])
    client = DownClient([])
    agent = Agent(client=client, model="m", reasoning_effort="")

    agent.respond([], "oi")
    assert len(client.calls) == 1
    agent.respond([], "oi de novo")  # within 60 s: no API call, instant fallback
    assert len(client.calls) == 1

    clock[0] += agent_module.CIRCUIT_OPEN_S + 1
    answer = FakeItem(
        type="message", role="assistant", content=[{"type": "output_text", "text": "Oi!"}]
    )
    agent.client = FakeClient([response([answer], "Oi!")])  # API is back
    result = agent.respond([], "oi")
    assert result.reply == "Oi!" and result.degraded is False


def test_empty_model_answer_uses_fallback():
    agent = Agent(client=FakeClient([response([], "")]), model="m", reasoning_effort="")
    assert agent.respond([], "oi").degraded is True
