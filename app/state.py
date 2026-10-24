"""应用状态：按当前用户设置构建向量库与 LLM 客户端，设置变更后自动重建。"""

import threading
from typing import Callable

import chromadb
from chromadb.config import Settings as ChromaSettings

from .config import Settings
from .embeddings import embedding_signature, make_embedding_function
from .fetcher import Fetcher
from .history import ProfileHistory
from .llm import LLMClient, make_llm
from .user_settings import EmbeddingSettings, LLMSettings, SettingsStore, UserSettings
from .vectorstore import VectorStore

StoreFactory = Callable[[EmbeddingSettings], VectorStore]
LLMFactory = Callable[[LLMSettings], LLMClient]


class AppState:
    def __init__(
        self,
        config: Settings,
        settings_store: SettingsStore | None = None,
        store_factory: StoreFactory | None = None,
        llm_factory: LLMFactory | None = None,
        fetcher: Fetcher | None = None,
        history: ProfileHistory | None = None,
    ):
        self.config = config
        self.settings_store = settings_store or SettingsStore(config.settings_file)
        self.fetcher = fetcher or Fetcher(timeout=config.fetch_timeout, user_agent=config.user_agent)
        self.history = history or ProfileHistory(config.profiles_dir)
        self._store_factory = store_factory or self._default_store
        self._llm_factory = llm_factory or (lambda s: make_llm(s, config.llm_max_tokens))
        self._lock = threading.Lock()
        self._chroma: chromadb.ClientAPI | None = None
        self._store: tuple[tuple, VectorStore] | None = None

    def user_settings(self) -> UserSettings:
        return self.settings_store.load()

    def save_settings(self, settings: UserSettings) -> None:
        self.settings_store.save(settings)

    def _default_store(self, emb: EmbeddingSettings) -> VectorStore:
        if self._chroma is None:
            self.config.chroma_dir.mkdir(parents=True, exist_ok=True)
            self._chroma = chromadb.PersistentClient(
                path=str(self.config.chroma_dir), settings=ChromaSettings(anonymized_telemetry=False)
            )
        name = f"{self.config.collection_name}_{embedding_signature(emb)}"
        return VectorStore(self._chroma, name, make_embedding_function(emb))

    def store(self) -> VectorStore:
        emb = self.user_settings().embedding
        key = (emb.provider, emb.base_url, emb.model, emb.api_key, emb.batch_size)
        with self._lock:
            if self._store is None or self._store[0] != key:
                self._store = (key, self._store_factory(emb))
            return self._store[1]

    def llm(self) -> LLMClient:
        # 客户端构建开销很小，每次按最新设置创建
        return self.llm_for(self.user_settings().llm)

    def llm_for(self, settings: LLMSettings) -> LLMClient:
        return self._llm_factory(settings)
