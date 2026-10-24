"""ChromaDB 向量库封装：按企业隔离检索，保存来源元数据用于引用。"""

import hashlib
import math
import re
from typing import Any

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction, register_embedding_function

from .models import Chunk, SearchHit


@register_embedding_function
class HashEmbeddingFunction(EmbeddingFunction[Documents]):
    """离线可用的字符 n-gram 哈希向量，无需下载模型；语义能力有限，适合测试与演示。"""

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


def make_embedding_function(backend: str) -> EmbeddingFunction:
    if backend == "hash":
        return HashEmbeddingFunction()
    return DefaultEmbeddingFunction()


def _metadata(chunk: Chunk) -> dict[str, Any]:
    meta = chunk.model_dump(exclude={"id", "text"})
    return {k: v for k, v in meta.items() if v is not None}  # Chroma 不接受 None


class VectorStore:
    def __init__(self, client: chromadb.ClientAPI, collection_name: str, embedding_function: EmbeddingFunction):
        self._collection = client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_function,
            metadata={"hnsw:space": "cosine"},
        )

    @classmethod
    def persistent(cls, path: str, collection_name: str, backend: str) -> "VectorStore":
        return cls(chromadb.PersistentClient(path=path), collection_name, make_embedding_function(backend))

    def add_chunks(self, chunks: list[Chunk], batch_size: int = 128) -> None:
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            self._collection.upsert(
                ids=[c.id for c in batch],
                documents=[c.text for c in batch],
                metadatas=[_metadata(c) for c in batch],
            )

    def delete_source(self, company: str, url: str) -> None:
        """重新入库同一 URL 前清掉旧切片，避免内容变短后残留过期片段。"""
        self._collection.delete(where={"$and": [{"company": company}, {"url": url}]})

    def search(self, company: str, query: str, top_k: int) -> list[SearchHit]:
        res = self._collection.query(
            query_texts=[query], n_results=top_k, where={"company": company},
            include=["documents", "metadatas", "distances"],
        )
        hits: list[SearchHit] = []
        for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]):
            chunk = Chunk(id=cid, text=doc, **meta)
            hits.append(SearchHit(chunk=chunk, distance=dist))
        return hits

    def companies(self) -> dict[str, int]:
        metas = self._collection.get(include=["metadatas"])["metadatas"] or []
        counts: dict[str, int] = {}
        for meta in metas:
            counts[meta["company"]] = counts.get(meta["company"], 0) + 1
        return counts

    def delete_company(self, company: str) -> None:
        self._collection.delete(where={"company": company})
