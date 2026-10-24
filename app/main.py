from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException

from .config import get_settings
from .fetcher import Fetcher
from .ingest import IngestService
from .llm import ClaudeClient, LLMError
from .models import CompanyProfile, IngestRequest, IngestResponse, ProfileRequest, SearchHit, SearchRequest
from .profiler import InsufficientDataError, Profiler
from .vectorstore import VectorStore

app = FastAPI(title="Firm Checker - 企业信息检索 RAG 助手", version="0.1.0")


@lru_cache
def get_store() -> VectorStore:
    s = get_settings()
    return VectorStore.persistent(s.chroma_dir, s.collection_name, s.embedding_backend)


@lru_cache
def get_fetcher() -> Fetcher:
    s = get_settings()
    return Fetcher(timeout=s.fetch_timeout, user_agent=s.user_agent)


@lru_cache
def get_llm() -> ClaudeClient:
    s = get_settings()
    return ClaudeClient(model=s.llm_model, effort=s.llm_effort, max_tokens=s.llm_max_tokens)


def get_ingest_service(store: VectorStore = Depends(get_store), fetcher: Fetcher = Depends(get_fetcher)) -> IngestService:
    s = get_settings()
    return IngestService(store, fetcher, s.chunk_size, s.chunk_overlap, s.max_crawl_pages)


def get_profiler(store: VectorStore = Depends(get_store), llm: ClaudeClient = Depends(get_llm)) -> Profiler:
    s = get_settings()
    return Profiler(store, llm, s.retrieval_top_k, s.max_context_chunks)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ingest", response_model=IngestResponse)
def ingest(req: IngestRequest, service: IngestService = Depends(get_ingest_service)) -> IngestResponse:
    if not req.urls and not req.documents:
        raise HTTPException(422, "provide at least one url or document")
    return service.ingest(req)


@app.post("/search", response_model=list[SearchHit])
def search(req: SearchRequest, store: VectorStore = Depends(get_store)) -> list[SearchHit]:
    return store.search(req.company, req.query, req.top_k)


@app.post("/profile", response_model=CompanyProfile)
def profile(req: ProfileRequest, profiler: Profiler = Depends(get_profiler)) -> CompanyProfile:
    try:
        return profiler.generate(req.company, req.language)
    except InsufficientDataError as exc:
        raise HTTPException(404, str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/companies")
def companies(store: VectorStore = Depends(get_store)) -> dict[str, int]:
    """已入库的企业及其切片数量。"""
    return store.companies()


@app.delete("/companies/{company}")
def delete_company(company: str, store: VectorStore = Depends(get_store)) -> dict[str, str]:
    store.delete_company(company)
    return {"deleted": company}
