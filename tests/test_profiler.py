import pytest

from app.ingest import IngestService
from app.models import IngestRequest
from app.profiler import PROFILE_SCHEMA, InsufficientDataError, Profiler
from tests.conftest import FakeLLM


def _ingest(store, fetcher):
    IngestService(store, fetcher, 200, 50, 5).ingest(
        IngestRequest(company="Acme", urls=["https://acme.example/"], crawl=True)
    )


def test_profile_resolves_citations_and_drops_unsupported(store, fetcher):
    _ingest(store, fetcher)
    llm = FakeLLM({
        "summary": {"text": "Acme 是深圳的工业机器人公司。", "source_ids": ["S1", "S99"]},
        "business_lines": [
            {"name": "智能制造", "description": "智能制造事业部", "source_ids": ["S1"]},
            {"name": "编造业务", "description": "无来源", "source_ids": ["S42"]},
        ],
        "product_categories": [{"name": "协作机器人", "description": "主要产品", "source_ids": ["S2", "S2"]}],
        "target_markets": [],
    })
    profiler = Profiler(store, llm, top_k=4, max_context_chunks=10)
    profile = profiler.generate("Acme")

    system, prompt, schema = llm.calls[0]
    assert schema is PROFILE_SCHEMA
    assert '<source id="S1"' in prompt and "Acme" in prompt

    assert [i.name for i in profile.business_lines] == ["智能制造"]
    assert len(profile.product_categories[0].citations) == 1  # 去重
    citation = profile.business_lines[0].citations[0]
    assert citation.url.startswith("https://acme.example/")
    assert citation.snippet
    assert [c.source_id for c in profile.summary_citations] == ["S1"]
    assert any("S99" in w for w in profile.warnings)
    assert any("编造业务" in w for w in profile.warnings)
    assert profile.model == "fake-llm"


def test_retrieve_dedupes_and_caps(store, fetcher):
    _ingest(store, fetcher)
    profiler = Profiler(store, FakeLLM({}), top_k=10, max_context_chunks=2)
    chunks = profiler.retrieve("Acme")
    assert len(chunks) == 2
    assert len({c.id for c in chunks}) == 2


def test_no_data_raises(store):
    with pytest.raises(InsufficientDataError):
        Profiler(store, FakeLLM({}), 4, 10).generate("Nobody")


def test_schema_is_strict():
    def walk(node):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
            for child in node["properties"].values():
                walk(child)
        if node.get("type") == "array":
            walk(node["items"])

    walk(PROFILE_SCHEMA)
