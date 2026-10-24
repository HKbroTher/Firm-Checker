import uuid

import chromadb
import httpx
import pytest

from app.fetcher import Fetcher
from app.vectorstore import HashEmbeddingFunction, VectorStore

PAGES = {
    "https://acme.example/": """<html><head><title>Acme 官网</title></head><body>
        <nav>首页 | 关于</nav>
        <main><h1>Acme 科技</h1><p>Acme 科技成立于2010年，总部位于深圳，是一家工业机器人公司。</p>
        <a href="/products">产品中心</a><a href="https://other.example/x">外链</a></main>
        <script>var x = 1;</script></body></html>""",
    "https://acme.example/products": """<html><head><title>产品中心</title></head><body><main>
        <p>主要产品包括协作机器人、AGV 移动机器人和机器视觉系统。</p>
        <p>业务板块分为智能制造事业部和物流自动化事业部。</p></main></body></html>""",
}


def _handler(request: httpx.Request) -> httpx.Response:
    body = PAGES.get(str(request.url))
    if body is None:
        return httpx.Response(404, text="not found")
    return httpx.Response(200, text=body, headers={"content-type": "text/html; charset=utf-8"})


@pytest.fixture
def fetcher() -> Fetcher:
    return Fetcher(timeout=5, user_agent="test", client=httpx.Client(transport=httpx.MockTransport(_handler)))


@pytest.fixture
def store() -> VectorStore:
    client = chromadb.EphemeralClient()
    return VectorStore(client, f"test_{uuid.uuid4().hex}", HashEmbeddingFunction())


class FakeLLM:
    model = "fake-llm"

    def __init__(self, response: dict):
        self.response = response
        self.calls: list[tuple[str, str, dict]] = []

    def generate_json(self, system, prompt, schema):
        self.calls.append((system, prompt, schema))
        return self.response
