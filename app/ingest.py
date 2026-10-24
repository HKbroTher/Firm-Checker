"""入库流程：抓取 / 接收文本 → 切分 → 写入向量库。"""

from .chunking import chunk_document
from .fetcher import Fetcher
from .models import IngestFailure, IngestRequest, IngestResponse, RawDocument
from .vectorstore import VectorStore


class IngestService:
    def __init__(self, store: VectorStore, fetcher: Fetcher, chunk_size: int, chunk_overlap: int, max_crawl_pages: int):
        self.store = store
        self.fetcher = fetcher
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_crawl_pages = max_crawl_pages

    def _store_document(self, doc: RawDocument) -> int:
        chunks = chunk_document(doc, self.chunk_size, self.chunk_overlap)
        self.store.delete_source(doc.company, doc.url)
        self.store.add_chunks(chunks)
        return len(chunks)

    def ingest(self, req: IngestRequest) -> IngestResponse:
        docs = chunks = 0
        failures: list[IngestFailure] = []

        for item in req.documents:
            doc = RawDocument(company=req.company, **item.model_dump())
            chunks += self._store_document(doc)
            docs += 1

        seeds = [str(u) for u in req.urls]
        for url, doc, error in self.fetcher.crawl(req.company, seeds, req.crawl, self.max_crawl_pages):
            if doc is None:
                failures.append(IngestFailure(url=url, error=error or "unknown error"))
                continue
            chunks += self._store_document(doc)
            docs += 1

        return IngestResponse(company=req.company, documents=docs, chunks=chunks, failures=failures)
