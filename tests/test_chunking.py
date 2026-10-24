import pytest

from app.chunking import chunk_document, split_text
from app.models import RawDocument


def test_short_text_single_chunk():
    assert split_text("你好。\n世界。", chunk_size=100, overlap=10) == ["你好。\n世界。"]


def test_chunks_respect_size_and_overlap():
    text = "\n".join(f"第{i}句话，内容用于测试切分逻辑。" for i in range(60))
    chunks = split_text(text, chunk_size=120, overlap=40)
    assert len(chunks) > 1
    assert all(len(c) <= 120 for c in chunks)
    # 相邻块之间存在重叠内容
    assert chunks[0].splitlines()[-1] in chunks[1]


def test_long_paragraph_split_by_sentence_and_hard_split():
    text = "这是一句。" * 50 + "x" * 500
    chunks = split_text(text, chunk_size=100, overlap=20)
    assert all(len(c) <= 100 for c in chunks)
    assert "".join(chunks).count("x") >= 500


def test_invalid_overlap():
    with pytest.raises(ValueError):
        split_text("abc", chunk_size=10, overlap=10)


def test_chunk_document_ids_are_stable():
    doc = RawDocument(company="Acme", url="https://a/x", title="t", text="a\n" * 10)
    a = chunk_document(doc, 800, 100)
    b = chunk_document(doc, 800, 100)
    assert [c.id for c in a] == [c.id for c in b]
    assert a[0].company == "Acme" and a[0].url == "https://a/x"
