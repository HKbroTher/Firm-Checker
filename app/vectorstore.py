"""ChromaDB 向量库封装：按企业隔离检索，保存来源元数据用于引用。"""

from typing import Any

import chromadb
from chromadb.api.types import EmbeddingFunction
from chromadb.config import Settings as ChromaSettings

from .models import Chunk, SearchHit


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
    def persistent(cls, path: str, collection_name: str, embedding_function: EmbeddingFunction) -> "VectorStore":
        client = chromadb.PersistentClient(path=path, settings=ChromaSettings(anonymized_telemetry=False))
        return cls(client, collection_name, embedding_function)

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
