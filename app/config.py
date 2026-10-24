"""运行参数（切分、检索、抓取等）。API 服务商与密钥由用户在界面中设置，见 user_settings.py。"""

from functools import lru_cache
from pathlib import Path

from platformdirs import user_data_dir
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "Seek"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SEEK_", extra="ignore")

    # 数据目录：用户设置、向量库、历史画像都存放在这里
    data_dir: Path = Path(user_data_dir(APP_NAME, appauthor=False))
    collection_name: str = "company_docs"

    llm_max_tokens: int = 16000

    chunk_size: int = 800
    chunk_overlap: int = 150

    # 检索：每个画像维度的召回条数，以及送入 LLM 的来源片段上限
    retrieval_top_k: int = 6
    max_context_chunks: int = 24

    # 抓取
    fetch_timeout: float = 20.0
    max_crawl_pages: int = 10
    user_agent: str = "Seek/0.2 (+company research assistant)"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def settings_file(self) -> Path:
        return self.data_dir / "settings.json"

    @property
    def profiles_dir(self) -> Path:
        return self.data_dir / "profiles"


@lru_cache
def get_settings() -> Settings:
    return Settings()
