import json

import anthropic
import httpx2
import pytest

from app.llm import ClaudeClient, LLMError


def _client(reply: dict, captured: list) -> ClaudeClient:
    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append((request.headers, json.loads(request.content)))
        return httpx2.Response(200, json=reply)

    sdk = anthropic.Anthropic(api_key="test", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    return ClaudeClient(model="claude-opus-5-5", effort="medium", max_tokens=1000, client=sdk)


def _message(stop_reason: str, text: str) -> dict:
    return {
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": text}], "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


def test_request_shape_and_parse():
    captured: list = []
    llm = _client(_message("end_turn", '{"ok": true}'), captured)
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}
    assert llm.generate_json("sys", "hi", schema) == {"ok": True}

    headers, body = captured[0]
    assert body["model"] == "claude-opus-5-5"
    assert body["output_config"] == {"effort": "medium", "format": {"type": "json_schema", "schema": schema}}
    assert body["thinking"] == {"type": "adaptive"}
    assert body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in headers["anthropic-beta"]


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_bad_stop_reasons_raise(stop_reason):
    with pytest.raises(LLMError):
        _client(_message(stop_reason, "{}"), []).generate_json("s", "p", {})
