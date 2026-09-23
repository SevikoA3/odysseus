import asyncio

import httpx
import pytest

from src import llm_core


OPENAI = "https://api.openai.com/v1/chat/completions"
CLAUDE = "https://api.anthropic.com"


@pytest.mark.parametrize("url,model,expected", [
    (OPENAI, "gpt-5.6-sol", ("none", "low", "medium", "high", "xhigh", "max")),
    (OPENAI, "gpt-5.1", ("none", "low", "medium", "high")),
    (OPENAI, "gpt-5", ("minimal", "low", "medium", "high")),
    (OPENAI, "gpt-4.1", ()),
    (CLAUDE, "claude-sonnet-4-6", ("low", "medium", "high", "max")),
    (CLAUDE, "claude-opus-4-8", ("low", "medium", "high", "xhigh", "max")),
    (CLAUDE, "claude-sonnet-4-5", ()),
    ("http://localhost:8000/v1", "gpt-5.6-sol", ()),
])
def test_levels_follow_provider_and_model(url, model, expected):
    assert llm_core.thinking_levels_for(url, model) == expected


def test_openai_agent_tools_only_offer_accepted_effort():
    assert llm_core.thinking_levels_for(OPENAI, "gpt-5.6-sol", tools=True) == ("none",)
    assert llm_core.thinking_levels_for(OPENAI, "gpt-6-sol", tools=True) == ("none",)
    assert llm_core.thinking_levels_for(OPENAI, "gpt-6-astra", tools=True) == ()
    payload = {"tools": [{"type": "function"}], "reasoning_effort": "high"}
    llm_core._scrub_openai_chat_tool_reasoning(payload, OPENAI, "gpt-6-sol")
    assert payload["reasoning_effort"] == "none"
    assert "high" in llm_core.thinking_levels_for(
        "https://openrouter.ai/api/v1", "openai/gpt-5.6-sol", tools=True
    )


def test_claude_adaptive_payload_omits_temperature():
    payload = llm_core._build_anthropic_payload(
        "claude-sonnet-4-6", [{"role": "user", "content": "hi"}], 0.3, 4096,
        thinking_level="medium",
    )
    assert payload["thinking"] == {"type": "adaptive"}
    assert payload["output_config"] == {"effort": "medium"}
    assert "temperature" not in payload


def test_chatgpt_responses_uses_reasoning_object():
    payload = llm_core._build_chatgpt_responses_payload(
        "gpt-5.6-sol", [{"role": "user", "content": "hi"}], 0.3, 0,
        thinking_level="high",
    )
    assert payload["reasoning"] == {"effort": "high"}


def test_anthropic_stream_replays_signed_thinking_with_tool_result(monkeypatch):
    events = [
        {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "Need a tool"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "signed"}},
        {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "t1", "name": "search"}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "{}"}},
        {"type": "message_stop"},
    ]

    class Stream:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def aiter_lines(self):
            import json
            for event in events:
                yield "data: " + json.dumps(event)

    class Client:
        def stream(self, *args, **kwargs):
            return Stream()

    monkeypatch.setattr(llm_core, "_get_http_client", lambda: Client())

    async def collect():
        return [chunk async for chunk in llm_core.stream_llm(
            CLAUDE, "claude-sonnet-4-6", [{"role": "user", "content": "hi"}],
            thinking_level="medium",
        )]

    import json
    chunks = asyncio.run(collect())
    assert any('"thinking": true' in chunk and "Need a tool" in chunk for chunk in chunks)
    event = next(json.loads(chunk[6:]) for chunk in chunks if '"type": "tool_calls"' in chunk)
    messages = [
        {"role": "assistant", "content": None, "tool_calls": [{
            "id": "t1", "type": "function", "function": {"name": "search", "arguments": "{}"},
        }], "anthropic_thinking_blocks": event["anthropic_thinking_blocks"]},
        {"role": "tool", "tool_call_id": "t1", "content": "result"},
    ]
    sanitized = llm_core._sanitize_llm_messages(messages, anthropic=True)
    payload = llm_core._build_anthropic_payload("claude-sonnet-4-6", sanitized, 0.3, 4096)
    assert payload["messages"][0]["content"][0] == {
        "type": "thinking", "thinking": "Need a tool", "signature": "signed",
    }
    assert "anthropic_thinking_blocks" not in llm_core._sanitize_llm_messages(messages)


def test_async_chat_payload_and_cache_distinguish_levels(monkeypatch):
    llm_core._response_cache.clear()
    posted = []

    async def fake_post(client, url, headers, json, timeout):
        posted.append(json)
        return httpx.Response(
            200, request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": "OK"}}]},
        )

    monkeypatch.setattr(llm_core, "_get_http_client", lambda: object())
    monkeypatch.setattr(llm_core, "httpx_post_kimi_aware_async", fake_post)

    async def run():
        for level in ("low", "high"):
            assert await llm_core.llm_call_async(
                OPENAI, "gpt-5.6-sol", [{"role": "user", "content": "hi"}],
                max_retries=1, thinking_level=level,
            ) == "OK"

    asyncio.run(run())
    assert [p["reasoning_effort"] for p in posted] == ["low", "high"]
