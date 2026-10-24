from types import SimpleNamespace

import chromadb
import pytest

from app.embeddings import (
    ApiEmbeddingFunction,
    EmbeddingConfigError,
    HashEmbeddingFunction,
    embedding_signature,
    make_embedding_function,
)
from app.models import Chunk
from app.user_settings import EmbeddingSettings
from app.vectorstore import VectorStore


class FakeEmbeddingsAPI:
    """模拟 /embeddings 接口，打乱返回顺序以验证按 index 排序。"""

    def __init__(self):
        self.batches: list[list[str]] = []
        self.embeddings = SimpleNamespace(create=self.create)

    def create(self, model, input):
        self.batches.append(input)
        hasher = HashEmbeddingFunction(dim=64)
        data = [SimpleNamespace(index=i, embedding=hasher._embed(t)) for i, t in enumerate(input)]
        return SimpleNamespace(data=list(reversed(data)))


def test_api_embedding_batches_and_order():
    fake = FakeEmbeddingsAPI()
    ef = ApiEmbeddingFunction("https://api.siliconflow.cn/v1", "BAAI/bge-m3", batch_size=2, client=fake)
    texts = ["协作机器人", "欧洲市场", "物流自动化"]
    vectors = ef(texts)
    assert [len(b) for b in fake.batches] == [2, 1]
    expected = HashEmbeddingFunction(dim=64)
    assert vectors[0] == pytest.approx(expected._embed(texts[0]))
    assert "api_key" not in ef.get_config()


def test_api_embedding_store_roundtrip():
    ef = ApiEmbeddingFunction("u", "m", client=FakeEmbeddingsAPI())
    store = VectorStore(chromadb.EphemeralClient(), "t_api", ef)
    store.add_chunks([
        Chunk(id="a", company="Acme", text="协作机器人产品线", url="u", title="t", source_type="webpage", chunk_index=0),
        Chunk(id="b", company="Acme", text="海外市场与欧洲客户", url="u", title="t", source_type="webpage", chunk_index=1),
    ])
    assert store.search("Acme", "欧洲市场", top_k=1)[0].chunk.id == "b"


def test_make_embedding_function_requires_key():
    with pytest.raises(EmbeddingConfigError):
        make_embedding_function(EmbeddingSettings(api_key=""))
    assert isinstance(make_embedding_function(EmbeddingSettings(api_key="k")), ApiEmbeddingFunction)


def test_signature_differs_per_model():
    a = embedding_signature(EmbeddingSettings(model="BAAI/bge-m3"))
    b = embedding_signature(EmbeddingSettings(model="text-embedding-3-small", base_url="https://api.openai.com/v1"))
    assert a != b
    assert embedding_signature(EmbeddingSettings(provider="local")) == "local-minilm"
    assert all(c.isalnum() or c in "-" for c in a)
