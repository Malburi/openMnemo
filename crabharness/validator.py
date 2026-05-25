"""WorkerResult 검증 — 해시 무결성, 청크 수, space 분류."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from crabharness.codex_workers.base_worker import WorkerResult, WorkerStatus

# MetaOntology 허용 space
_VALID_SPACES = frozenset(
    ["subject", "resource", "evidence", "concept",
     "claim", "community", "outcome", "lever", "policy"]
)
_DEFAULT_SPACE = "evidence"


@dataclass
class ValidationReport:
    source: str
    passed: bool
    space: str
    issues: list[str] = field(default_factory=list)
    chunk_count: int = 0
    content_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source":       self.source,
            "passed":       self.passed,
            "space":        self.space,
            "issues":       self.issues,
            "chunk_count":  self.chunk_count,
            "content_hash": self.content_hash,
        }


class Validator:
    """
    WorkerResult를 받아 ValidationReport를 반환합니다.

    검증 항목:
    1. Worker 실행 상태 확인 (FAILED 이면 즉시 불합격)
    2. 콘텐츠 해시 재계산 → 일치 여부 확인
    3. 최소 청크 수 충족 여부
    4. space 분류 (메타데이터 힌트 또는 소스 패턴으로 결정)
    """

    def __init__(self, min_chunks: int = 1) -> None:
        self._min_chunks = min_chunks

    def validate(self, result: WorkerResult) -> ValidationReport:
        issues: list[str] = []

        # 1. Worker 실패 확인
        if result.status == WorkerStatus.FAILED:
            return ValidationReport(
                source       = result.source,
                passed       = False,
                space        = _DEFAULT_SPACE,
                issues       = [f"Worker 실패: {result.error}"],
                chunk_count  = 0,
                content_hash = "",
            )

        # 2. 해시 무결성
        recomputed = hashlib.sha256("".join(result.chunks).encode()).hexdigest()
        if recomputed != result.content_hash:
            issues.append("content_hash 불일치 — 데이터 변조 가능성")

        # 3. 최소 청크 수
        if result.chunk_count < self._min_chunks:
            issues.append(
                f"청크 수 부족: {result.chunk_count} < {self._min_chunks}"
            )

        # 4. space 분류
        space = _classify_space(result)

        passed = len(issues) == 0
        return ValidationReport(
            source       = result.source,
            passed       = passed,
            space        = space,
            issues       = issues,
            chunk_count  = result.chunk_count,
            content_hash = result.content_hash,
            metadata     = result.metadata,
        )

    def validate_all(self, results: list[WorkerResult]) -> list[ValidationReport]:
        return [self.validate(r) for r in results]


# ── space 분류 로직 ──────────────────────────────────────────────────────────

def _classify_space(result: WorkerResult) -> str:
    # 메타데이터에 명시된 경우 우선 사용
    hint = result.metadata.get("space", "")
    if hint in _VALID_SPACES:
        return hint

    # 소스 패턴 기반 휴리스틱
    src = result.source.lower()
    if src.endswith(".pdf") or src.endswith(".docx") or src.endswith(".txt"):
        return "resource"
    if src.startswith("http"):
        return "resource"

    # 청크 내용 키워드 힌트
    combined = " ".join(result.chunks[:3]).lower()
    if any(kw in combined for kw in ["policy", "regulation", "rule", "법", "규정"]):
        return "policy"
    if any(kw in combined for kw in ["claim", "assert", "hypothesis", "주장", "가설"]):
        return "claim"
    if any(kw in combined for kw in ["concept", "definition", "개념", "정의"]):
        return "concept"

    return _DEFAULT_SPACE
