from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


# ---------- 入库 ----------

class RawDocument(BaseModel):
    """一份待入库的公开资料（官网页面、新闻稿等）。"""

    company: str
    url: str
    title: str = ""
    source_type: str = "webpage"  # webpage / press_release / report / other
    text: str
    published_at: str | None = None


class Chunk(BaseModel):
    id: str
    company: str
    text: str
    url: str
    title: str
    source_type: str
    chunk_index: int
    published_at: str | None = None


class TextDocumentIn(BaseModel):
    url: str = Field(description="资料来源地址，用于引用展示")
    title: str = ""
    source_type: str = "press_release"
    text: str
    published_at: str | None = None


class IngestRequest(BaseModel):
    company: str
    urls: list[HttpUrl] = Field(default_factory=list, description="直接抓取的页面")
    crawl: bool = Field(False, description="是否沿同域链接继续抓取（数量受 MAX_CRAWL_PAGES 限制）")
    documents: list[TextDocumentIn] = Field(default_factory=list, description="已获取的文本资料，如新闻稿全文")


class IngestFailure(BaseModel):
    url: str
    error: str


class IngestResponse(BaseModel):
    company: str
    documents: int
    chunks: int
    failures: list[IngestFailure] = Field(default_factory=list)


# ---------- 检索 ----------

class SearchRequest(BaseModel):
    company: str
    query: str
    top_k: int = Field(5, ge=1, le=50)


class SearchHit(BaseModel):
    chunk: Chunk
    distance: float


# ---------- 画像 ----------

class Citation(BaseModel):
    source_id: str
    url: str
    title: str
    snippet: str


class ProfileItem(BaseModel):
    name: str
    description: str
    citations: list[Citation]


class CompanyProfile(BaseModel):
    company: str
    summary: str
    summary_citations: list[Citation]
    business_lines: list[ProfileItem]
    product_categories: list[ProfileItem]
    target_markets: list[ProfileItem]
    generated_at: datetime
    model: str
    warnings: list[str] = Field(default_factory=list)


class ProfileRequest(BaseModel):
    company: str
    language: str = Field("zh", description="画像输出语言，如 zh / en")
