"""Agent loop tests with a fake OpenAI client (no network, no API key)."""

from types import SimpleNamespace

from emporio.agent import Agent, visible_messages
from emporio.memory import ConversationStore


class FakeItem(SimpleNamespace):
    def model_dump(self, **_):
        return {k: v for k, v in vars(self).items() if v is not None}


def response(output, text=""):
    usage = SimpleNamespace(
        input_tokens=100, output_tokens=10, input_tokens_details=SimpleNamespace(cached_tokens=80)
    )
    return SimpleNamespace(output=output, output_text=text, usage=usage)


class FakeClient:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.calls = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return next(self._responses)


def test_agent_runs_tool_and_returns_answer():
    call = FakeItem(
        type="function_call",
        call_id="c1",
        name="search_products",
        arguments='{"query": "Takamine GD20", "category": null, "max_price": null, '
        '"min_price": null, "only_available": false}',
    )
    answer = FakeItem(
        type="message",
        role="assistant",
        content=[{"type": "output_text", "text": "Custa R$ 2.199,00."}],
    )
    client = FakeClient([response([call]), response([answer], "Custa R$ 2.199,00.")])
    agent = Agent(client=client, model="test-model", reasoning_effort="")

    result = agent.respond([], "Quanto custa o Takamine GD20?")

    assert result.reply == "Custa R$ 2.199,00."
    assert [e.name for e in result.tool_events] == ["search_products"]
    assert result.tool_events[0].result["results"][0]["list_price"] == "R$ 2.199,00"
    # 2nd request must carry the tool output back to the model
    second_input = client.calls[1]["input"]
    assert second_input[-1]["type"] == "function_call_output"
    assert "reasoning" not in client.calls[0]
    assert result.usage["cached_tokens"] == 160
    assert visible_messages(result.new_items) == [
        ("user", "Quanto custa o Takamine GD20?"),
        ("assistant", "Custa R$ 2.199,00."),
    ]


def test_conversation_store_roundtrip(tmp_path):
    store = ConversationStore(tmp_path / "c.db")
    store.append(
        "s1",
        [
            {"role": "user", "content": "oi"},
            {"type": "message", "role": "assistant", "content": []},
        ],
    )
    assert len(store.load("s1")) == 2
    assert store.load("other") == []
    assert store.user_message_count("s1") == 1


def test_daily_message_count(tmp_path):
    store = ConversationStore(tmp_path / "c.db")
    store.append("a", [{"role": "user", "content": "oi"}])
    store.append("b", [{"role": "user", "content": "oi"}, {"type": "function_call_output"}])
    assert store.user_messages_today() == 2
