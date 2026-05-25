"""URL을 가져와 텍스트 청크로 변환하는 Worker."""

from __future__ import annotations

import re
from typing import Any

from .base_worker import BaseWorker

_URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)


class WebCrawler(BaseWorker):
    """
    HTTP(S) URL → HTML 파싱 → 텍스트 청크.

    의존성: httpx (이미 포함), beautifulsoup4 (선택적).
    bs4 없이도 동작하지만 품질 저하.
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        timeout: float = 15.0,
        max_chars: int = 200_000,
    ) -> None:
        self._chunk_size    = chunk_size
        self._chunk_overlap = chunk_overlap
        self._timeout       = timeout
        self._max_chars     = max_chars

    @property
    def name(self) -> str:
        return "web_crawler"

    def can_handle(self, source: str) -> bool:
        return bool(_URL_PATTERN.match(source))

    def _extract(self, source: str, **_kwargs: Any) -> tuple[list[str], dict[str, Any]]:
        html, status_code = _fetch(source, self._timeout)
        text = _parse_html(html)[: self._max_chars]

        if not text.strip():
            raise RuntimeError(f"페이지에서 텍스트를 추출할 수 없습니다: {source}")

        from openmnemo.ontology.normalize import split_text_to_chunks
        chunks = split_text_to_chunks(text, self._chunk_size, self._chunk_overlap)

        metadata: dict[str, Any] = {
            "url":         source,
            "status_code": status_code,
            "char_count":  len(text),
        }
        return chunks, metadata


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _fetch(url: str, timeout: float) -> tuple[str, int]:
    try:
        import httpx
    except ImportError as e:
        raise RuntimeError("httpx 패키지가 필요합니다: pip install httpx") from e

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url, headers={"User-Agent": "CrabHarness/0.1"})
        resp.raise_for_status()
        return resp.text, resp.status_code


def _parse_html(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)
    except ImportError:
        # bs4 없으면 태그만 제거하는 단순 처리
        return re.sub(r"<[^>]+>", " ", html)
