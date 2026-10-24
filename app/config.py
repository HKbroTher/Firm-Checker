from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_model: str = "claude-opus-5-5"
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    llm_max_tokens: int = 16000

    chroma_dir: str = "./data/chroma"
    collection_name: str = "company_docs"
    # bge-m3：多语言（含中文）向量模型，1024 维；default：Chroma 内置 all-MiniLM-L6-v2（英文为主）；hash：离线测试用
    embedding_backend: Literal["bge-m3", "default", "hash"] = "bge-m3"
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cpu"  # 有 GPU 时设为 cuda

    chunk_size: int = 800
    chunk_overlap: int = 150

    # 检索：每个画像维度的召回条数，以及送入 LLM 的来源片段上限
    retrieval_top_k: int = 6
    max_context_chunks: int = 24

    # 抓取
    fetch_timeout: float = 20.0
    max_crawl_pages: int = 10
    user_agent: str = "FirmChecker/0.1 (+company research bot)"


@lru_cache
def get_settings() -> Settings:
    return Settings()
