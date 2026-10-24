"""LLM 调用层：使用 Claude 结构化输出（JSON Schema）生成企业画像。"""

import json
from typing import Any, Protocol

import anthropic


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    model: str

    def generate_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]: ...


class ClaudeClient:
    def __init__(self, model: str, effort: str, max_tokens: int, client: anthropic.Anthropic | None = None):
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self._client = client or anthropic.Anthropic()

    def generate_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.beta.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
                # 安全分类器拒答时由服务端按类别自动切换到推荐的后备模型重试
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.RateLimitError as exc:
            raise LLMError(f"LLM rate limited: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"LLM API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"LLM connection error: {exc}") from exc

        if response.stop_reason == "refusal":
            raise LLMError("LLM declined the request")
        if response.stop_reason == "max_tokens":
            raise LLMError("LLM output truncated (max_tokens reached)")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise LLMError("LLM returned no text content")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM returned invalid JSON: {exc}") from exc
