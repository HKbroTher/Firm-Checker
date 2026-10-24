"""抓取公开网页并抽取正文。"""

import logging
from urllib.parse import urljoin, urldefrag, urlparse

import httpx
from bs4 import BeautifulSoup

from .models import RawDocument

logger = logging.getLogger(__name__)

_NOISE_TAGS = ["script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "iframe"]
_SKIP_EXT = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".zip", ".mp4", ".css", ".js", ".xml")
# 爬取时优先跟进的链接关键词：关于我们、产品、业务、新闻
_PRIORITY_HINTS = ("about", "product", "solution", "service", "business", "news", "press", "investor",
                   "关于", "产品", "解决方案", "业务", "新闻", "投资者")


def extract_text(html: str) -> tuple[str, str, list[str]]:
    """返回 (标题, 正文, 页面内链接)。"""
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string or "").strip() if soup.title else ""
    links = [a["href"] for a in soup.find_all("a", href=True)]
    for tag in soup(_NOISE_TAGS):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    lines = (line.strip() for line in root.get_text("\n").splitlines())
    text = "\n".join(line for line in lines if line)
    return title, text, links


def _same_site_links(base_url: str, hrefs: list[str]) -> list[str]:
    host = urlparse(base_url).netloc
    seen: set[str] = set()
    result: list[str] = []
    for href in hrefs:
        url = urldefrag(urljoin(base_url, href)).url
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or parsed.netloc != host:
            continue
        if parsed.path.lower().endswith(_SKIP_EXT) or url in seen:
            continue
        seen.add(url)
        result.append(url)
    result.sort(key=lambda u: not any(h in u.lower() for h in _PRIORITY_HINTS))
    return result


def _guess_source_type(url: str) -> str:
    lower = url.lower()
    if any(k in lower for k in ("news", "press", "新闻")):
        return "press_release"
    return "webpage"


class Fetcher:
    def __init__(self, timeout: float, user_agent: str, client: httpx.Client | None = None):
        self._client = client or httpx.Client(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": user_agent}
        )

    def fetch(self, company: str, url: str) -> tuple[RawDocument, list[str]]:
        resp = self._client.get(url)
        resp.raise_for_status()
        if "html" not in resp.headers.get("content-type", "text/html"):
            raise ValueError(f"unsupported content-type: {resp.headers.get('content-type')}")
        title, text, hrefs = extract_text(resp.text)
        if not text.strip():
            raise ValueError("no text content extracted")
        final_url = str(resp.url)
        doc = RawDocument(
            company=company, url=final_url, title=title or final_url,
            source_type=_guess_source_type(final_url), text=text,
        )
        return doc, _same_site_links(final_url, hrefs)

    def crawl(self, company: str, seeds: list[str], crawl: bool, max_pages: int):
        """依次产出 (url, RawDocument | None, error | None)。"""
        queue = list(seeds)
        visited: set[str] = set()
        fetched = 0
        while queue and fetched < max_pages:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            try:
                doc, links = self.fetch(company, url)
            except Exception as exc:  # noqa: BLE001 - 单页失败不影响整体
                logger.warning("fetch failed %s: %s", url, exc)
                yield url, None, str(exc)
                continue
            visited.add(doc.url)
            fetched += 1
            yield url, doc, None
            if crawl:
                queue.extend(link for link in links if link not in visited)
