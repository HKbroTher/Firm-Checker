import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.llm import LLMConfigError, LLMError
from app.main import app, get_state
from app.state import AppState
from app.user_settings import SettingsStore
from tests.conftest import FakeLLM

PROFILE = {
    "summary": {"text": "工业机器人公司", "source_ids": ["S1"]},
    "business_lines": [], "product_categories": [],
    "target_markets": [{"name": "制造业", "description": "工厂客户", "source_ids": ["S1"]}],
}


class FailingLLM(FakeLLM):
    def __init__(self, exc):
        super().__init__({})
        self.exc = exc

    def generate_json(self, system, prompt, schema):
        raise self.exc


@pytest.fixture
def make_client(tmp_path, store, fetcher):
    def factory(llm):
        config = Settings(data_dir=tmp_path)
        state = AppState(config, SettingsStore(config.settings_file), store_factory=lambda emb: store,
                         llm_factory=lambda s: llm, fetcher=fetcher)
        app.dependency_overrides = {get_state: lambda: state}
        return TestClient(app)

    yield factory
    app.dependency_overrides = {}


def test_end_to_end(make_client):
    client = make_client(FakeLLM(PROFILE))

    assert client.post("/api/ingest", json={"company": "Acme"}).status_code == 422
    r = client.post("/api/ingest", json={
        "company": "Acme", "urls": ["https://acme.example/"],
        "documents": [{"url": "https://news.example/1", "title": "新闻稿", "text": "Acme 发布新一代协作机器人，面向欧洲市场。"}],
    })
    assert r.status_code == 200 and r.json()["documents"] == 2

    assert client.get("/api/companies").json()["Acme"] >= 2
    hits = client.post("/api/search", json={"company": "Acme", "query": "欧洲市场", "top_k": 3}).json()
    assert hits and hits[0]["chunk"]["company"] == "Acme"

    assert client.get("/api/profile/Acme").status_code == 404
    profile = client.post("/api/profile", json={"company": "Acme"}).json()
    assert profile["target_markets"][0]["citations"][0]["source_id"] == "S1"
    # 画像已保存，可以直接读取
    assert client.get("/api/profile/Acme").json()["summary"] == "工业机器人公司"

    assert client.post("/api/profile", json={"company": "Nobody"}).status_code == 404
    assert client.delete("/api/companies/Acme").status_code == 200
    assert "Acme" not in client.get("/api/companies").json()
    assert client.get("/api/profile/Acme").status_code == 404


def test_llm_errors_map_to_status(make_client):
    client = make_client(FailingLLM(LLMError("boom")))
    client.post("/api/ingest", json={"company": "Acme", "urls": ["https://acme.example/"]})
    assert client.post("/api/profile", json={"company": "Acme"}).status_code == 502

    client = make_client(FailingLLM(LLMConfigError("请先在「设置」中填写")))
    client.post("/api/ingest", json={"company": "Acme", "urls": ["https://acme.example/"]})
    r = client.post("/api/profile", json={"company": "Acme"})
    assert r.status_code == 400 and "设置" in r.json()["detail"]


def test_settings_endpoints(make_client, tmp_path):
    client = make_client(FakeLLM({"ok": True}))
    assert client.get("/api/settings").json()["llm"]["has_api_key"] is False
    assert "claude" in client.get("/api/presets").json()["llm"]

    body = {
        "llm": {"preset": "claude", "provider": "anthropic", "api_key": "sk-ant-abcdefgh1234", "base_url": "", "model": "claude-opus-5-5"},
        "embedding": {"preset": "local", "provider": "local", "api_key": "", "base_url": "", "model": "all-MiniLM-L6-v2", "batch_size": 10},
    }
    saved = client.put("/api/settings", json=body).json()
    assert saved["llm"]["has_api_key"] is True and "api_key" not in saved["llm"]
    assert "sk-ant-abcdefgh1234" in (tmp_path / "settings.json").read_text()

    # 留空密钥 = 保持不变
    body["llm"]["api_key"] = ""
    body["llm"]["model"] = "claude-sonnet-5-5"
    saved = client.put("/api/settings", json=body).json()
    assert saved["llm"]["has_api_key"] is True and saved["llm"]["model"] == "claude-sonnet-5-5"

    # 测试连接：LLM 用注入的假实现；向量化填了 api 但没有 key
    body["embedding"] = {"preset": "siliconflow", "provider": "api", "api_key": "", "base_url": "https://api.siliconflow.cn/v1",
                         "model": "BAAI/bge-m3", "batch_size": 10}
    result = client.post("/api/settings/test", json=body).json()
    assert result["llm"]["ok"] is True
    assert result["embedding"]["ok"] is False and "API Key" in result["embedding"]["message"]


def test_static_ui_served(make_client):
    client = make_client(FakeLLM({}))
    r = client.get("/")
    assert r.status_code == 200 and "<title>Seek</title>" in r.text
    assert client.get("/app.js").status_code == 200
