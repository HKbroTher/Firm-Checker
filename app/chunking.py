"""文本切分：先按段落，过长段落再按句子，最后按长度打包并保留重叠。"""

import hashlib
import re

from .models import Chunk, RawDocument

_SENTENCE_END = re.compile(r"(?<=[。！？!?；;])|(?<=\.)\s+")


def _split_sentences(paragraph: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(paragraph) if s and s.strip()]


def _hard_split(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def split_text(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    # 1. 切成不超过 chunk_size 的最小单元（段落 → 句子 → 硬切）
    units: list[str] = []
    for para in re.split(r"\n\s*\n|\n", text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= chunk_size:
            units.append(para)
            continue
        for sent in _split_sentences(para):
            units.extend(_hard_split(sent, chunk_size) if len(sent) > chunk_size else [sent])

    # 2. 贪心打包，新块以上一块末尾的若干单元作为重叠
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for unit in units:
        if current and length + len(unit) + 1 > chunk_size:
            chunks.append("\n".join(current))
            tail: list[str] = []
            tail_len = 0
            for prev in reversed(current):
                if tail_len + len(prev) + 1 > overlap:
                    break
                tail.insert(0, prev)
                tail_len += len(prev) + 1
            # 重叠部分加上新单元仍超长时，从头丢弃重叠
            while tail and tail_len + len(unit) + 1 > chunk_size:
                tail_len -= len(tail.pop(0)) + 1
            current, length = tail, tail_len
        current.append(unit)
        length += len(unit) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def chunk_document(doc: RawDocument, chunk_size: int, overlap: int) -> list[Chunk]:
    doc_key = hashlib.sha1(f"{doc.company}|{doc.url}".encode()).hexdigest()[:16]
    return [
        Chunk(
            id=f"{doc_key}-{i}",
            company=doc.company,
            text=piece,
            url=doc.url,
            title=doc.title,
            source_type=doc.source_type,
            chunk_index=i,
            published_at=doc.published_at,
        )
        for i, piece in enumerate(split_text(doc.text, chunk_size, overlap))
    ]
