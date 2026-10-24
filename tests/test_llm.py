import json

import anthropic
import httpx2
import pytest

from app.llm import ClaudeClient, LLMError


def _client(reply: dict, captured: list, model: str = "claude-opus-5-5") -> ClaudeClient:
    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append((request.headers, json.loads(request.content)))
        return httpx2.Response(200, json=reply)

    sdk = anthropic.Anthropic(api_key="test", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    return ClaudeClient(model=model, max_tokens=1000, client=sdk)


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


def test_fallback_only_for_supported_models():
    captured: list = []
    _client(_message("end_turn", "{}"), captured, model="claude-haiku-5-5").generate_json("s", "p", {})
    headers, body = captured[0]
    assert "fallbacks" not in body
    assert "server-side-fallback" not in headers.get("anthropic-beta", "")


# ---------- 兼容 OpenAI 接口的服务 ----------

from types import SimpleNamespace  # noqa: E402

import httpx  # noqa: E402
import openai  # noqa: E402

from app.llm import LLMConfigError, OpenAICompatibleClient, make_llm  # noqa: E402
from app.user_settings import LLMSettings  # noqa: E402


class FakeChat:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content, finish = self.replies.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish, message=SimpleNamespace(content=content))])


def test_openai_compatible_json_mode_and_schema_in_prompt():
    fake = FakeChat([('{"ok": true}', "stop")])
    llm = OpenAICompatibleClient("deepseek-chat", 4000, client=fake)
    assert llm.generate_json("sys", "hi", {"type": "object", "properties": {"ok": {"type": "boolean"}}}) == {"ok": True}
    call = fake.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert call["model"] == "deepseek-chat"
    assert '"ok"' in call["messages"][0]["content"]  # schema 写进了系统提示


def test_openai_compatible_retries_invalid_json_once():
    fake = FakeChat([("not json", "stop"), ('{"a": 1}', "stop")])
    assert OpenAICompatibleClient("m", 100, client=fake).generate_json("s", "p", {}) == {"a": 1}
    assert len(fake.calls) == 2
    assert fake.calls[1]["messages"][-1]["role"] == "user"


def test_openai_compatible_truncation_raises():
    fake = FakeChat([('{"a":', "length")])
    with pytest.raises(LLMError):
        OpenAICompatibleClient("m", 100, client=fake).generate_json("s", "p", {})


def test_make_llm_requires_key_and_picks_provider():
    with pytest.raises(LLMConfigError):
        make_llm(LLMSettings(api_key=""), 16000)
    claude = make_llm(LLMSettings(api_key="k"), 16000)
    assert isinstance(claude, ClaudeClient)
    ds = make_llm(LLMSettings(preset="deepseek", provider="openai_compatible", api_key="k",
                              base_url="https://api.deepseek.com", model="deepseek-chat"), 16000)
    assert isinstance(ds, OpenAICompatibleClient) and ds.max_tokens == 8192
    with pytest.raises(LLMConfigError):
        make_llm(LLMSettings(provider="openai_compatible", api_key="k", base_url="", model="m"), 16000)


class RejectsJsonMode(FakeChat):
    """模拟不支持 response_format 的服务。"""

    def create(self, **kwargs):
        if "response_format" in kwargs:
            self.calls.append(kwargs)
            req = httpx.Request("POST", "https://example.invalid/chat/completions")
            resp = httpx.Response(400, request=req, json={"error": {"message": "response_format unsupported"}})
            raise openai.BadRequestError("response_format unsupported", response=resp, body=None)
        return super().create(**kwargs)


def test_openai_compatible_falls_back_without_json_mode():
    fake = RejectsJsonMode([('```json\n{"ok": true}\n```', "stop"), ('{"n": 2}', "stop")])
    llm = OpenAICompatibleClient("gemini-2.5-flash", 4000, client=fake)
    assert llm.generate_json("s", "p", {}) == {"ok": True}  # 去掉 JSON 模式重试，并剥离代码块
    assert "response_format" in fake.calls[0] and "response_format" not in fake.calls[1]
    # 记住该服务不支持 JSON 模式，后续请求不再尝试
    assert llm.generate_json("s", "p", {}) == {"n": 2}
    assert "response_format" not in fake.calls[2]


def test_strip_code_fence():
    from app.llm import _strip_code_fence

    assert _strip_code_fence('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert _strip_code_fence('{"a": 1}') == '{"a": 1}'
