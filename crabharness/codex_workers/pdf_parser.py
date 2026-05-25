"""PDF 파일을 텍스트 청크로 변환하는 Worker."""

from __future__ import annotations

import os
from typing import Any

from .base_worker import BaseWorker


class PdfParser(BaseWorker):
    """
    로컬 PDF 파일 → 텍스트 청크.

    의존성: pypdf (pyproject.toml에 이미 포함).
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50) -> None:
        self._chunk_size    = chunk_size
        self._chunk_overlap = chunk_overlap

    @property
    def name(self) -> str:
        return "pdf_parser"

    def can_handle(self, source: str) -> bool:
        return source.lower().endswith(".pdf") and os.path.isfile(source)

    def score(self, source: str) -> float:
        if not self.can_handle(source):
            return 0.0
        size_mb = os.path.getsize(source) / (1024 * 1024)
        # 50 MB 이상이면 처리 신뢰도 감소
        return max(0.3, 1.0 - size_mb / 100)

    def _extract(self, source: str, **_kwargs: Any) -> tuple[list[str], dict[str, Any]]:
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise RuntimeError("pypdf 패키지가 필요합니다: pip install pypdf") from e

        reader   = PdfReader(source)
        pages    = reader.pages
        n_pages  = len(pages)

        full_text = "\n".join(
            page.extract_text() or "" for page in pages
        ).strip()

        if not full_text:
            raise RuntimeError(f"PDF에서 텍스트를 추출할 수 없습니다: {source}")

        chunks = _chunk_text(full_text, self._chunk_size, self._chunk_overlap)

        metadata: dict[str, Any] = {
            "page_count": n_pages,
            "file_size":  os.path.getsize(source),
            "file_name":  os.path.basename(source),
        }
        return chunks, metadata


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """단순 문자 단위 슬라이딩-윈도우 청킹."""
    from openmnemo.ontology.normalize import split_text_to_chunks
    return split_text_to_chunks(text, chunk_size=size, chunk_overlap=overlap)
