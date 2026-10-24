from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .config import get_settings
from .embeddings import EmbeddingConfigError, EmbeddingError, make_embedding_function
from .ingest import IngestService
from .llm import LLMConfigError, LLMError
from .models import CompanyProfile, IngestRequest, IngestResponse, ProfileRequest, SearchHit, SearchRequest
from .profiler import InsufficientDataError, Profiler
from .state import AppState
from .user_settings import EMBEDDING_PRESETS, LLM_PRESETS, UserSettings, merge_update, public_view

STATIC_DIR = Path(__file__).parent / "static"

_state: AppState | None = None


def get_state() -> AppState:
    global _state
    if _state is None:
        _state = AppState(get_settings())
    return _state


def _service_error(exc: Exception) -> HTTPException:
    """设置类问题返回 400（界面引导去设置页），服务调用失败返回 502。"""
    if isinstance(exc, (LLMConfigError, EmbeddingConfigError)):
        return HTTPException(400, str(exc))
    return HTTPException(502, str(exc))


api = APIRouter(prefix="/api")


@api.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------- 设置 ----------

@api.get("/presets")
def presets() -> dict:
    return {"llm": LLM_PRESETS, "embedding": EMBEDDING_PRESETS}


@api.get("/settings")
def read_settings(state: AppState = Depends(get_state)) -> dict:
    return public_view(state.user_settings())


@api.put("/settings")
def update_settings(update: UserSettings, state: AppState = Depends(get_state)) -> dict:
    merged = merge_update(state.user_settings(), update)
    state.save_settings(merged)
    return public_view(merged)


class CheckResult(BaseModel):
    ok: bool
    message: str


@api.post("/settings/test")
def test_settings(candidate: UserSettings, state: AppState = Depends(get_state)) -> dict[str, CheckResult]:
    """用界面上尚未保存的设置测试连通性；密钥留空时使用已保存的密钥。"""
    settings = merge_update(state.user_settings(), candidate)
    results: dict[str, CheckResult] = {}

    try:
        llm = state.llm_for(settings.llm)
        schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"],
                  "additionalProperties": False}
        llm.generate_json("你是连通性测试助手。", '请返回 {"ok": true}', schema)
        results["llm"] = CheckResult(ok=True, message=f"连接成功（{settings.llm.model}）")
    except Exception as exc:  # noqa: BLE001 - 原样展示给用户
        results["llm"] = CheckResult(ok=False, message=str(exc))

    try:
        vector = make_embedding_function(settings.embedding)(["连通性测试"])[0]
        results["embedding"] = CheckResult(ok=True, message=f"连接成功（{settings.embedding.model}，{len(vector)} 维）")
    except Exception as exc:  # noqa: BLE001
        results["embedding"] = CheckResult(ok=False, message=str(exc))
    return results


# ---------- 资料 ----------

@api.post("/ingest", response_model=IngestResponse)
def ingest(req: IngestRequest, state: AppState = Depends(get_state)) -> IngestResponse:
    if not req.urls and not req.documents:
        raise HTTPException(422, "请至少提供一个网址或一段文本资料")
    c = state.config
    try:
        service = IngestService(state.store(), state.fetcher, c.chunk_size, c.chunk_overlap, c.max_crawl_pages)
        return service.ingest(req)
    except EmbeddingError as exc:
        raise _service_error(exc) from exc


@api.post("/search", response_model=list[SearchHit])
def search(req: SearchRequest, state: AppState = Depends(get_state)) -> list[SearchHit]:
    try:
        return state.store().search(req.company, req.query, req.top_k)
    except EmbeddingError as exc:
        raise _service_error(exc) from exc


@api.get("/companies")
def companies(state: AppState = Depends(get_state)) -> dict[str, int]:
    """当前向量模型下已入库的企业及其切片数量。"""
    try:
        return state.store().companies()
    except EmbeddingError as exc:
        raise _service_error(exc) from exc


@api.delete("/companies/{company}")
def delete_company(company: str, state: AppState = Depends(get_state)) -> dict[str, str]:
    try:
        state.store().delete_company(company)
    except EmbeddingError as exc:
        raise _service_error(exc) from exc
    state.history.delete(company)
    return {"deleted": company}


# ---------- 画像 ----------

@api.post("/profile", response_model=CompanyProfile)
def profile(req: ProfileRequest, state: AppState = Depends(get_state)) -> CompanyProfile:
    try:
        profiler = Profiler(state.store(), state.llm(), state.config.retrieval_top_k, state.config.max_context_chunks)
        result = profiler.generate(req.company, req.language)
    except InsufficientDataError as exc:
        raise HTTPException(404, f"还没有「{req.company}」的资料，请先在「资料入库」中添加") from exc
    except (LLMError, EmbeddingError) as exc:
        raise _service_error(exc) from exc
    state.history.save(result)
    return result


@api.get("/profile/{company}", response_model=CompanyProfile)
def last_profile(company: str, state: AppState = Depends(get_state)) -> CompanyProfile:
    saved = state.history.load(company)
    if saved is None:
        raise HTTPException(404, "暂无历史画像")
    return saved


app = FastAPI(title="Seek - 企业信息检索 RAG 助手", version=__version__)
app.include_router(api)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
