"""用户在界面中填写的 API 设置：LLM 服务商与向量化服务商，保存在本机数据目录。"""

import json
import os
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

LLMProvider = Literal["anthropic", "openai_compatible"]
EmbeddingProvider = Literal["api", "local"]

# 预设只用于在界面中自动填充，用户可以修改地址和模型名
LLM_PRESETS: dict[str, dict] = {
    "claude": {
        "label": "Claude (Anthropic)",
        "provider": "anthropic",
        "base_url": "",
        "models": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
        "key_url": "https://console.anthropic.com/settings/keys",
    },
    "deepseek": {
        "label": "DeepSeek",
        "provider": "openai_compatible",
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-chat"],
        "key_url": "https://platform.deepseek.com/api_keys",
    },
    "qwen": {
        "label": "通义千问（阿里云百炼）",
        "provider": "openai_compatible",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-max", "qwen-turbo"],
        "key_url": "https://bailian.console.aliyun.com/?apiKey=1",
    },
    "gemini": {
        "label": "Google Gemini",
        "provider": "openai_compatible",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro"],
        "key_url": "https://aistudio.google.com/apikey",
    },
    "openai": {
        "label": "OpenAI",
        "provider": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4.1-mini", "gpt-4.1"],
        "key_url": "https://platform.openai.com/api-keys",
    },
    "custom": {
        "label": "自定义（兼容 OpenAI 接口）",
        "provider": "openai_compatible",
        "base_url": "",
        "models": [],
        "key_url": "",
    },
}

EMBEDDING_PRESETS: dict[str, dict] = {
    "siliconflow": {
        "label": "硅基流动 bge-m3（免费，中文推荐）",
        "provider": "api",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": ["BAAI/bge-m3"],
        "key_url": "https://cloud.siliconflow.cn/account/ak",
    },
    "qwen": {
        "label": "通义千问 text-embedding",
        "provider": "api",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["text-embedding-v3"],
        "key_url": "https://bailian.console.aliyun.com/?apiKey=1",
    },
    "gemini": {
        "label": "Google Gemini embedding",
        "provider": "api",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "models": ["gemini-embedding-001"],
        "key_url": "https://aistudio.google.com/apikey",
    },
    "openai": {
        "label": "OpenAI embedding",
        "provider": "api",
        "base_url": "https://api.openai.com/v1",
        "models": ["text-embedding-3-small", "text-embedding-3-large"],
        "key_url": "https://platform.openai.com/api-keys",
    },
    "custom": {
        "label": "自定义（兼容 OpenAI 接口）",
        "provider": "api",
        "base_url": "",
        "models": [],
        "key_url": "",
    },
    "local": {
        "label": "本地小模型（离线，英文为主，首次使用下载约 80MB）",
        "provider": "local",
        "base_url": "",
        "models": ["all-MiniLM-L6-v2"],
        "key_url": "",
    },
}


class LLMSettings(BaseModel):
    preset: str = "claude"
    provider: LLMProvider = "anthropic"
    api_key: str = ""
    base_url: str = ""
    model: str = "claude-opus-5-5"


class EmbeddingSettings(BaseModel):
    preset: str = "siliconflow"
    provider: EmbeddingProvider = "api"
    api_key: str = ""
    base_url: str = "https://api.siliconflow.cn/v1"
    model: str = "BAAI/bge-m3"
    batch_size: int = Field(10, ge=1, le=256)


class UserSettings(BaseModel):
    llm: LLMSettings = Field(default_factory=LLMSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)


def _mask(key: str) -> str:
    if not key:
        return ""
    return f"{key[:3]}…{key[-4:]}" if len(key) > 10 else "已填写"


def public_view(settings: UserSettings) -> dict:
    """返回给界面的设置：不回传密钥明文。"""
    data = settings.model_dump()
    for section in ("llm", "embedding"):
        key = data[section].pop("api_key")
        data[section]["has_api_key"] = bool(key)
        data[section]["api_key_hint"] = _mask(key)
    return data


def merge_update(current: UserSettings, update: UserSettings) -> UserSettings:
    """界面提交时 api_key 留空表示保留原密钥（仅限未切换服务商时，避免把 A 家的 key 发给 B 家）。"""
    merged = update.model_copy(deep=True)
    if not merged.llm.api_key and merged.llm.preset == current.llm.preset:
        merged.llm.api_key = current.llm.api_key
    if not merged.embedding.api_key and merged.embedding.preset == current.embedding.preset:
        merged.embedding.api_key = current.embedding.api_key
    return merged


class SettingsStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def load(self) -> UserSettings:
        try:
            return UserSettings.model_validate_json(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return UserSettings()

    def save(self, settings: UserSettings) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(settings.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                os.chmod(tmp, 0o600)  # 文件包含 API Key，仅当前用户可读
            except OSError:
                pass
            os.replace(tmp, self.path)
