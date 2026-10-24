"""LLM 调用层：Claude 使用官方 SDK 与结构化输出；DeepSeek、通义千问、OpenAI 等走兼容 OpenAI 的接口。"""

import json
from typing import Any, Protocol

import anthropic
import openai

from .user_settings import LLMSettings


class LLMError(RuntimeError):
    pass


class LLMConfigError(LLMError):
    """设置不完整（如未填写 API Key），需要用户去设置页处理。"""


class LLMClient(Protocol):
    model: str

    def generate_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]: ...


# 支持服务端拒答回退（fallbacks: "default"）的 Claude 模型
_CLAUDE_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}


class ClaudeClient:
    def __init__(self, model: str, max_tokens: int, effort: str = "medium",
                 api_key: str | None = None, client: anthropic.Anthropic | None = None):
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self._client = client or anthropic.Anthropic(api_key=api_key)

    def generate_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        extra: dict[str, Any] = {}
        if self.model in _CLAUDE_FALLBACK_MODELS:
            # 安全分类器拒答时由服务端按类别自动切换到推荐的后备模型重试
            extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        try:
            response = self._client.beta.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
                **extra,
            )
        except anthropic.AuthenticationError as exc:
            raise LLMConfigError("Claude API Key 无效，请在设置中检查") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError(f"Claude 请求过于频繁或额度不足：{exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Claude 接口返回错误 {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"无法连接 Claude 接口：{exc}") from exc

        if response.stop_reason == "refusal":
            raise LLMError("模型拒绝了本次请求")
        if response.stop_reason == "max_tokens":
            raise LLMError("模型输出被截断（达到 max_tokens 上限）")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise LLMError("模型没有返回文本内容")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"模型返回的 JSON 无法解析：{exc}") from exc


class OpenAICompatibleClient:
    """兼容 OpenAI Chat Completions 的服务。各家对 json_schema 的支持不一，统一使用 JSON 模式并在提示词中给出结构。"""

    def __init__(self, model: str, max_tokens: int, base_url: str = "", api_key: str = "", client: Any = None):
        self.model = model
        self.max_tokens = max_tokens
        self._client = client or openai.OpenAI(api_key=api_key, base_url=base_url or None, timeout=300)
        self._json_mode = True

    def _create(self, messages: list[dict]):
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "max_tokens": self.max_tokens}
        if self._json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            return self._client.chat.completions.create(**kwargs)
        except openai.BadRequestError:
            if not self._json_mode:
                raise
            # 部分服务（或其中部分模型）不支持 JSON 模式，去掉后重试；提示词已要求只输出 JSON
            self._json_mode = False
            kwargs.pop("response_format")
            return self._client.chat.completions.create(**kwargs)

    def _complete(self, messages: list[dict]) -> str:
        try:
            resp = self._create(messages)
        except openai.AuthenticationError as exc:
            raise LLMConfigError("API Key 无效，请在设置中检查") from exc
        except openai.NotFoundError as exc:
            raise LLMConfigError(f"模型或接口地址不存在，请检查设置：{exc.message}") from exc
        except openai.RateLimitError as exc:
            raise LLMError(f"请求过于频繁或额度不足：{exc.message}") from exc
        except openai.APIStatusError as exc:
            raise LLMError(f"接口返回错误 {exc.status_code}: {exc.message}") from exc
        except openai.APIConnectionError as exc:
            raise LLMError(f"无法连接接口：{exc}") from exc
        choice = resp.choices[0]
        if choice.finish_reason == "length":
            raise LLMError("模型输出被截断（达到 max_tokens 上限）")
        if choice.finish_reason == "content_filter":
            raise LLMError("模型服务商的内容审核拦截了本次请求")
        return _strip_code_fence(choice.message.content or "")

    def generate_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        system_full = (
            f"{system}\n\n只输出一个 JSON 对象，不要输出其他文字。JSON 必须符合以下 JSON Schema：\n"
            f"{json.dumps(schema, ensure_ascii=False)}"
        )
        messages = [{"role": "system", "content": system_full}, {"role": "user", "content": prompt}]
        text = self._complete(messages)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            # 偶尔返回不合法 JSON，带上错误信息重试一次
            messages += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": f"上面的输出不是合法 JSON（{exc}），请只输出修正后的 JSON 对象。"},
            ]
            text = self._complete(messages)
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc2:
                raise LLMError(f"模型返回的 JSON 无法解析：{exc2}") from exc2


def _strip_code_fence(text: str) -> str:
    """去掉模型偶尔包裹在 JSON 外面的 ```json 代码块标记。"""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def make_llm(settings: LLMSettings, max_tokens: int) -> LLMClient:
    if not settings.api_key:
        raise LLMConfigError("请先在「设置」中填写大模型的 API Key")
    if not settings.model:
        raise LLMConfigError("请先在「设置」中填写模型名")
    if settings.provider == "anthropic":
        return ClaudeClient(settings.model, max_tokens, api_key=settings.api_key)
    if not settings.base_url:
        raise LLMConfigError("请先在「设置」中填写接口地址")
    # 兼容接口的服务输出上限普遍较低（如 DeepSeek 为 8K）
    return OpenAICompatibleClient(settings.model, min(max_tokens, 8192), settings.base_url, settings.api_key)
