from fastapi.testclient import TestClient

from app.llm import LLMError
from app.main import app, get_fetcher, get_llm, get_store
from tests.conftest import FakeLLM


class FailingLLM(FakeLLM):
    def generate_json(self, system, prompt, schema):
        raise LLMError("boom")


def _client(store, fetcher, llm):
    app.dependency_overrides = {get_store: lambda: store, get_fetcher: lambda: fetcher, get_llm: lambda: llm}
    return TestClient(app)


def test_end_to_end(store, fetcher):
    llm = FakeLLM({
        "summary": {"text": "工业机器人公司", "source_ids": ["S1"]},
        "business_lines": [], "product_categories": [],
        "target_markets": [{"name": "制造业", "description": "工厂客户", "source_ids": ["S1"]}],
    })
    client = _client(store, fetcher, llm)

    assert client.post("/ingest", json={"company": "Acme"}).status_code == 422
    r = client.post("/ingest", json={
        "company": "Acme", "urls": ["https://acme.example/"],
        "documents": [{"url": "https://news.example/1", "title": "新闻稿", "text": "Acme 发布新一代协作机器人，面向欧洲市场。"}],
    })
    assert r.status_code == 200 and r.json()["documents"] == 2

    assert client.get("/companies").json()["Acme"] >= 2
    hits = client.post("/search", json={"company": "Acme", "query": "欧洲市场", "top_k": 3}).json()
    assert hits and hits[0]["chunk"]["company"] == "Acme"

    profile = client.post("/profile", json={"company": "Acme"}).json()
    assert profile["target_markets"][0]["citations"][0]["source_id"] == "S1"

    assert client.post("/profile", json={"company": "Nobody"}).status_code == 404
    assert client.delete("/companies/Acme").status_code == 200
    assert "Acme" not in client.get("/companies").json()
    app.dependency_overrides = {}


def test_llm_error_maps_to_502(store, fetcher):
    client = _client(store, fetcher, FailingLLM({}))
    client.post("/ingest", json={"company": "Acme", "urls": ["https://acme.example/"]})
    assert client.post("/profile", json={"company": "Acme"}).status_code == 502
    app.dependency_overrides = {}
