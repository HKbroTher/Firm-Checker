import sys
import types

import chromadb
import numpy as np
import pytest
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from app.models import Chunk
from app.vectorstore import HashEmbeddingFunction, VectorStore, collection_name_for, make_embedding_function


class FakeSentenceTransformer:
    """替代 sentence_transformers.SentenceTransformer，避免测试下载 bge-m3。"""

    instances: list["FakeSentenceTransformer"] = []

    def __init__(self, model_name_or_path, device, **kwargs):
        self.model_name_or_path = model_name_or_path
        self.device = device
        self.encode_kwargs: dict = {}
        FakeSentenceTransformer.instances.append(self)

    def encode(self, sentences, **kwargs):
        self.encode_kwargs = kwargs
        return np.array([HashEmbeddingFunction(dim=1024)._embed(s) for s in sentences], dtype=np.float32)


@pytest.fixture
def fake_sentence_transformers(monkeypatch):
    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    # Chroma 按模型名缓存已加载的模型，测试间需要清空
    monkeypatch.setattr(SentenceTransformerEmbeddingFunction, "models", {})
    FakeSentenceTransformer.instances.clear()


def test_bge_m3_backend(fake_sentence_transformers):
    ef = make_embedding_function("bge-m3", "BAAI/bge-m3", "cuda")
    assert isinstance(ef, SentenceTransformerEmbeddingFunction)
    model = FakeSentenceTransformer.instances[0]
    assert (model.model_name_or_path, model.device) == ("BAAI/bge-m3", "cuda")

    vectors = ef(["示例科技的主要产品是协作机器人"])
    assert len(vectors[0]) == 1024
    assert model.encode_kwargs["normalize_embeddings"] is True


def test_bge_m3_store_roundtrip(fake_sentence_transformers):
    ef = make_embedding_function("bge-m3")
    store = VectorStore(chromadb.EphemeralClient(), collection_name_for("t_bge", "bge-m3"), ef)
    store.add_chunks([
        Chunk(id="a", company="Acme", text="协作机器人产品线", url="u", title="t", source_type="webpage", chunk_index=0),
        Chunk(id="b", company="Acme", text="海外市场与欧洲客户", url="u", title="t", source_type="webpage", chunk_index=1),
    ])
    assert store.search("Acme", "欧洲市场", top_k=1)[0].chunk.id == "b"


def test_collection_name_per_backend():
    assert collection_name_for("company_docs", "bge-m3") != collection_name_for("company_docs", "default")
