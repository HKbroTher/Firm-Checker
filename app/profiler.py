"""RAG 画像生成：分维度检索 → 编号来源 → LLM 结构化输出 → 校验引用。"""

from datetime import datetime, timezone
from html import escape

from .llm import LLMClient
from .models import Chunk, Citation, CompanyProfile, ProfileItem
from .vectorstore import VectorStore

# 每个画像维度用多条中英文查询召回，提高官网/新闻稿混合语料下的覆盖率
ASPECT_QUERIES: dict[str, list[str]] = {
    "overview": ["公司简介 企业概况 成立 总部", "company overview about us mission headquarters"],
    "business_lines": ["主营业务 业务板块 事业部 收入构成", "business segments divisions lines of business revenue"],
    "product_categories": ["产品 解决方案 服务 产品线", "products solutions services offerings portfolio"],
    "target_markets": ["目标市场 客户 行业 区域 海外", "target markets customers industries regions countries"],
}

_SECTION_KEYS = ("business_lines", "product_categories", "target_markets")

_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "source_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["name", "description", "source_ids"],
    "additionalProperties": False,
}

PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "source_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["text", "source_ids"],
            "additionalProperties": False,
        },
        **{key: {"type": "array", "items": _ITEM_SCHEMA} for key in _SECTION_KEYS},
    },
    "required": ["summary", *_SECTION_KEYS],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """你是企业研究分析师，根据提供的公开资料片段为企业撰写结构化画像。

规则：
- 只使用资料片段中明确出现的信息，不要凭常识或记忆补充；资料没有覆盖的维度返回空数组。
- 每一项都必须在 source_ids 中列出支撑它的片段编号（如 "S3"），只能使用资料中给出的编号。
- business_lines：公司的业务板块/事业部；product_categories：具体的产品或服务类别；target_markets：面向的客户群体、行业或地理区域。
- 同一维度内合并重复项，name 简短，description 一到两句话说明依据。"""


class InsufficientDataError(RuntimeError):
    pass


class Profiler:
    def __init__(self, store: VectorStore, llm: LLMClient, top_k: int, max_context_chunks: int):
        self.store = store
        self.llm = llm
        self.top_k = top_k
        self.max_context_chunks = max_context_chunks

    def retrieve(self, company: str) -> list[Chunk]:
        """各维度查询结果轮流合并去重，保证每个维度都有片段进入上下文。"""
        per_query = [
            [hit.chunk for hit in self.store.search(company, q, self.top_k)]
            for queries in ASPECT_QUERIES.values()
            for q in queries
        ]
        selected: dict[str, Chunk] = {}
        for rank in range(self.top_k):
            for hits in per_query:
                if rank < len(hits) and hits[rank].id not in selected:
                    selected[hits[rank].id] = hits[rank]
                    if len(selected) >= self.max_context_chunks:
                        return list(selected.values())
        return list(selected.values())

    @staticmethod
    def build_prompt(company: str, sources: dict[str, Chunk], language: str) -> str:
        blocks = [
            f'<source id="{sid}" title="{escape(c.title)}" url="{escape(c.url)}" type="{c.source_type}">\n{c.text}\n</source>'
            for sid, c in sources.items()
        ]
        return (
            f"企业名称：{company}\n输出语言：{language}\n\n"
            "<sources>\n" + "\n\n".join(blocks) + "\n</sources>\n\n"
            "请基于以上资料生成企业画像。"
        )

    def generate(self, company: str, language: str = "zh") -> CompanyProfile:
        chunks = self.retrieve(company)
        if not chunks:
            raise InsufficientDataError(f"no documents ingested for company '{company}'")
        sources = {f"S{i}": c for i, c in enumerate(chunks, start=1)}
        raw = self.llm.generate_json(SYSTEM_PROMPT, self.build_prompt(company, sources, language), PROFILE_SCHEMA)

        warnings: list[str] = []

        def resolve(ids: list[str], where: str) -> list[Citation]:
            citations: list[Citation] = []
            for sid in dict.fromkeys(ids):
                chunk = sources.get(sid)
                if chunk is None:
                    warnings.append(f"{where}: dropped unknown source id '{sid}'")
                    continue
                citations.append(Citation(source_id=sid, url=chunk.url, title=chunk.title, snippet=chunk.text[:300]))
            return citations

        sections: dict[str, list[ProfileItem]] = {}
        for key in _SECTION_KEYS:
            items: list[ProfileItem] = []
            for item in raw.get(key, []):
                citations = resolve(item.get("source_ids", []), f"{key}/{item.get('name')}")
                if not citations:
                    # 没有可核验来源的结论不进入画像
                    warnings.append(f"{key}/{item.get('name')}: removed, no valid citation")
                    continue
                items.append(ProfileItem(name=item["name"], description=item["description"], citations=citations))
            sections[key] = items

        summary = raw.get("summary", {})
        return CompanyProfile(
            company=company,
            summary=summary.get("text", ""),
            summary_citations=resolve(summary.get("source_ids", []), "summary"),
            generated_at=datetime.now(timezone.utc),
            model=self.llm.model,
            warnings=warnings,
            **sections,
        )
