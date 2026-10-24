from app.fetcher import extract_text
from app.ingest import IngestService
from app.models import IngestRequest, TextDocumentIn


def test_extract_text_drops_noise():
    title, text, links = extract_text(
        "<html><title>T</title><body><nav>menu</nav><main><p>正文</p><a href='/a'>A</a></main>"
        "<script>evil()</script></body></html>"
    )
    assert title == "T"
    assert "正文" in text and "menu" not in text and "evil" not in text
    assert links == ["/a"]


def test_crawl_follows_same_site_links_only(fetcher, store):
    service = IngestService(store, fetcher, chunk_size=200, chunk_overlap=50, max_crawl_pages=5)
    res = service.ingest(IngestRequest(company="Acme", urls=["https://acme.example/"], crawl=True))
    assert res.documents == 2
    assert res.failures == []
    assert store.companies() == {"Acme": res.chunks}


def test_failures_are_reported(fetcher, store):
    service = IngestService(store, fetcher, 200, 50, 5)
    res = service.ingest(IngestRequest(company="Acme", urls=["https://acme.example/missing"]))
    assert res.documents == 0
    assert res.failures[0].url == "https://acme.example/missing"


def test_reingest_replaces_old_chunks(fetcher, store):
    service = IngestService(store, fetcher, chunk_size=50, chunk_overlap=10, max_crawl_pages=5)
    long_doc = TextDocumentIn(url="https://acme.example/news/1", text="\n".join(["新闻内容很长的一段文字。"] * 20))
    first = service.ingest(IngestRequest(company="Acme", documents=[long_doc]))
    short_doc = long_doc.model_copy(update={"text": "更新后的短新闻。"})
    service.ingest(IngestRequest(company="Acme", documents=[short_doc]))
    assert first.chunks > 1
    assert store.companies() == {"Acme": 1}


def test_search_is_scoped_by_company(store, fetcher):
    service = IngestService(store, fetcher, 200, 50, 5)
    service.ingest(IngestRequest(company="Acme", documents=[TextDocumentIn(url="u1", text="协作机器人产品")]))
    service.ingest(IngestRequest(company="Other", documents=[TextDocumentIn(url="u2", text="协作机器人产品")]))
    hits = store.search("Acme", "机器人", top_k=10)
    assert {h.chunk.company for h in hits} == {"Acme"}
