"""向量化：在线 API（兼容 OpenAI /embeddings 接口）、本地小模型、离线哈希（测试用）。"""

import hashlib
import math
import re
from typing import Any

import openai
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction, register_embedding_function

from .user_settings import EmbeddingSettings


class EmbeddingError(RuntimeError):
    pass


class EmbeddingConfigError(EmbeddingError):
    """设置不完整或密钥无效，需要用户去设置页处理。"""


@register_embedding_function
class ApiEmbeddingFunction(EmbeddingFunction[Documents]):
    """调用兼容 OpenAI 的 /embeddings 接口，如硅基流动 bge-m3、通义 text-embedding、OpenAI。"""

    def __init__(self, base_url: str, model: str, api_key: str = "", batch_size: int = 10, client: Any = None):
        self.base_url = base_url
        self.model = model
        self.batch_size = batch_size
        self._client = client or openai.OpenAI(api_key=api_key or "missing", base_url=base_url or None, timeout=60)

    def __call__(self, input: Documents) -> Embeddings:
        vectors: list[list[float]] = []
        for i in range(0, len(input), self.batch_size):
            batch = list(input[i : i + self.batch_size])
            try:
                resp = self._client.embeddings.create(model=self.model, input=batch)
            except openai.AuthenticationError as exc:
                raise EmbeddingConfigError("向量化 API Key 无效，请在设置中检查") from exc
            except openai.APIStatusError as exc:
                raise EmbeddingError(f"向量化接口返回错误 {exc.status_code}: {exc.message}") from exc
            except openai.APIConnectionError as exc:
                raise EmbeddingError(f"无法连接向量化接口：{exc}") from exc
            # 部分服务不保证返回顺序，按 index 排序
            vectors.extend(item.embedding for item in sorted(resp.data, key=lambda d: d.index))
        return vectors

    @staticmethod
    def name() -> str:
        return "firm_checker_api"

    def get_config(self) -> dict[str, Any]:
        # 不把 API Key 写入 Chroma 的集合配置
        return {"base_url": self.base_url, "model": self.model, "batch_size": self.batch_size}

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> "ApiEmbeddingFunction":
        return ApiEmbeddingFunction(config["base_url"], config["model"], batch_size=config.get("batch_size", 10))


@register_embedding_function
class HashEmbeddingFunction(EmbeddingFunction[Documents]):
    """离线可用的字符 n-gram 哈希向量，无需下载模型；语义能力有限，仅用于测试。"""

    def __init__(self, dim: int = 512):
        self.dim = dim

    def __call__(self, input: Documents) -> Embeddings:
        return [self._embed(text) for text in input]

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        text = text.lower()
        # 英文按单词、中文按字的 1/2-gram
        tokens = re.findall(r"[a-z0-9]+", text)
        cjk = re.findall(r"[一-鿿]", text)
        tokens += cjk + [a + b for a, b in zip(cjk, cjk[1:])]
        for tok in tokens:
            h = int.from_bytes(hashlib.md5(tok.encode()).digest()[:4], "little")
            vec[h % self.dim] += 1.0 if (h >> 31) == 0 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    @staticmethod
    def name() -> str:
        return "firm_checker_hash"

    def get_config(self) -> dict[str, Any]:
        return {"dim": self.dim}

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> "HashEmbeddingFunction":
        return HashEmbeddingFunction(dim=config.get("dim", 512))


def make_embedding_function(settings: EmbeddingSettings) -> EmbeddingFunction:
    if settings.provider == "local":
        return DefaultEmbeddingFunction()
    if not settings.api_key:
        raise EmbeddingConfigError("请先在「设置」中填写向量化服务的 API Key")
    if not settings.base_url or not settings.model:
        raise EmbeddingConfigError("请先在「设置」中填写向量化服务的接口地址和模型名")
    return ApiEmbeddingFunction(settings.base_url, settings.model, settings.api_key, settings.batch_size)


def embedding_signature(settings: EmbeddingSettings) -> str:
    """标识一种向量空间：不同服务或模型生成的向量不能混用，各自对应一个集合。"""
    if settings.provider == "local":
        return "local-minilm"
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", settings.model).strip("-").lower()[:40] or "model"
    digest = hashlib.sha1(f"{settings.base_url}|{settings.model}".encode()).hexdigest()[:8]
    return f"{slug}-{digest}"
