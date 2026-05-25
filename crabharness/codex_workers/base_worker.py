"""BaseWorker 추상 클래스 및 WorkerResult 데이터 모델."""

from __future__ import annotations

import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WorkerStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED  = "failed"


@dataclass
class WorkerResult:
    """하나의 Worker 실행 결과."""

    worker_name: str
    source: str
    chunks: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)
    status: WorkerStatus = WorkerStatus.SUCCESS
    error: str | None = None
    elapsed_sec: float = 0.0

    # 무결성 해시 — validator가 검증에 사용
    content_hash: str = field(init=False)

    def __post_init__(self) -> None:
        self.content_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        combined = "".join(self.chunks).encode("utf-8")
        return hashlib.sha256(combined).hexdigest()

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @property
    def ok(self) -> bool:
        return self.status != WorkerStatus.FAILED

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_name":   self.worker_name,
            "source":        self.source,
            "chunk_count":   self.chunk_count,
            "content_hash":  self.content_hash,
            "status":        self.status.value,
            "error":         self.error,
            "elapsed_sec":   round(self.elapsed_sec, 3),
            "metadata":      self.metadata,
        }


class BaseWorker(ABC):
    """
    CrabHarness 작업 단위 추상 기반.

    서브클래스는 `can_handle()`과 `process()`만 구현하면 됩니다.
    `run()`은 타이밍, 에러 래핑, WorkerResult 생성을 자동 처리합니다.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Worker 고유 이름 (예: "pdf_parser", "web_crawler")."""

    @abstractmethod
    def can_handle(self, source: str) -> bool:
        """이 Worker가 주어진 source를 처리할 수 있으면 True."""

    @abstractmethod
    def _extract(self, source: str, **kwargs: Any) -> tuple[list[str], dict[str, Any]]:
        """
        소스에서 청크 목록과 메타데이터를 반환합니다.
        실패 시 예외를 raise — run()이 WorkerStatus.FAILED로 잡습니다.
        """

    def run(self, source: str, **kwargs: Any) -> WorkerResult:
        """추출 실행 — 타이밍·에러 처리 포함."""
        start = time.monotonic()
        try:
            chunks, metadata = self._extract(source, **kwargs)
            status = WorkerStatus.SUCCESS if chunks else WorkerStatus.PARTIAL
            error  = None if chunks else "청크 없음"
        except Exception as exc:
            chunks   = []
            metadata = {}
            status   = WorkerStatus.FAILED
            error    = str(exc)

        elapsed = time.monotonic() - start
        return WorkerResult(
            worker_name  = self.name,
            source       = source,
            chunks       = chunks,
            metadata     = metadata,
            status       = status,
            error        = error,
            elapsed_sec  = elapsed,
        )

    def score(self, source: str) -> float:
        """
        Planner가 Worker 선택 우선순위에 사용하는 0~1 점수.
        기본값: can_handle이면 1.0, 아니면 0.0.
        서브클래스에서 신뢰도·비용 기반으로 오버라이드 가능.
        """
        return 1.0 if self.can_handle(source) else 0.0
