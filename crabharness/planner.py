"""Mission → DelegationJob 변환 플래너."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from crabharness.codex_workers.base_worker import BaseWorker
from crabharness.codex_workers.pdf_parser import PdfParser
from crabharness.codex_workers.web_crawler import WebCrawler


# ── 도메인 모델 ───────────────────────────────────────────────────────────────

@dataclass
class Mission:
    """Harness 에 전달되는 최상위 작업 명세."""

    sources: list[str]
    goal: str = "ingest"
    options: dict[str, Any] = field(default_factory=dict)
    mission_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass
class DelegationJob:
    """단일 소스에 대해 선택된 Worker와 실행 옵션."""

    job_id: str
    mission_id: str
    source: str
    worker: BaseWorker
    worker_score: float
    options: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id":       self.job_id,
            "mission_id":   self.mission_id,
            "source":       self.source,
            "worker":       self.worker.name,
            "worker_score": round(self.worker_score, 3),
        }


# ── 플래너 ────────────────────────────────────────────────────────────────────

class Planner:
    """
    Mission을 받아 각 source에 최적 Worker를 배정하고
    DelegationJob 목록을 반환합니다.

    등록된 Worker가 없거나 점수가 0인 source는 건너뜁니다.
    """

    def __init__(self, workers: list[BaseWorker] | None = None) -> None:
        self._workers: list[BaseWorker] = workers if workers is not None else _default_workers()

    def register(self, worker: BaseWorker) -> None:
        self._workers.append(worker)

    def plan(self, mission: Mission) -> list[DelegationJob]:
        jobs: list[DelegationJob] = []

        for source in mission.sources:
            best_worker, best_score = self._select(source)
            if best_worker is None or best_score == 0.0:
                continue

            jobs.append(DelegationJob(
                job_id       = uuid.uuid4().hex[:12],
                mission_id   = mission.mission_id,
                source       = source,
                worker       = best_worker,
                worker_score = best_score,
                options      = dict(mission.options),
            ))

        return jobs

    def _select(self, source: str) -> tuple[BaseWorker | None, float]:
        best: BaseWorker | None = None
        best_score = 0.0
        for w in self._workers:
            s = w.score(source)
            if s > best_score:
                best_score = s
                best        = w
        return best, best_score


def _default_workers() -> list[BaseWorker]:
    return [PdfParser(), WebCrawler()]
