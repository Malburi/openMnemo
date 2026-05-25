"""CrabHarness — Mission 실행 파이프라인 진입점."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from crabharness.codex_workers.base_worker import WorkerResult
from crabharness.planner import DelegationJob, Mission, Planner
from crabharness.promotion import PackResult, Promoter
from crabharness.validator import ValidationReport, Validator

logger = logging.getLogger(__name__)


@dataclass
class HarnessResult:
    mission_id: str
    jobs: list[DelegationJob]
    worker_results: list[WorkerResult]
    reports: list[ValidationReport]
    pack: PackResult | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.reports if r.passed)

    @property
    def failed_count(self) -> int:
        return len(self.reports) - self.passed_count

    def summary(self) -> dict[str, Any]:
        return {
            "mission_id":    self.mission_id,
            "total_sources": len(self.jobs),
            "passed":        self.passed_count,
            "failed":        self.failed_count,
            "pack":          self.pack.to_dict() if self.pack else None,
            "errors":        self.errors,
        }


class CrabHarness:
    """
    Mission → Plan → Execute → Validate → Promote 파이프라인.

    사용 예:
        harness = CrabHarness()
        result  = harness.run(Mission(sources=["paper.pdf", "https://example.com"]))
        print(result.summary())
    """

    def __init__(
        self,
        planner:  Planner  | None = None,
        validator: Validator | None = None,
        promoter:  Promoter  | None = None,
    ) -> None:
        self._planner   = planner   or Planner()
        self._validator = validator or Validator(min_chunks=1)
        self._promoter  = promoter  or Promoter()

    def run(
        self,
        mission: Mission,
        output_path: str | None = None,
    ) -> HarnessResult:
        logger.info("CrabHarness 시작 — mission_id=%s, sources=%d",
                    mission.mission_id, len(mission.sources))

        # 1. 계획 수립
        jobs = self._planner.plan(mission)
        logger.info("계획 완료: %d개 Job 배정", len(jobs))

        if not jobs:
            return HarnessResult(
                mission_id     = mission.mission_id,
                jobs           = [],
                worker_results = [],
                reports        = [],
                errors         = ["처리 가능한 소스가 없습니다."],
            )

        # 2. Worker 실행
        worker_results: list[WorkerResult] = []
        errors: list[str] = []
        for job in jobs:
            logger.info("실행: worker=%s source=%s", job.worker.name, job.source)
            result = job.worker.run(job.source, **job.options)
            worker_results.append(result)
            if not result.ok:
                errors.append(f"[{job.source}] {result.error}")

        # 3. 검증
        reports = self._validator.validate_all(worker_results)
        logger.info("검증 완료: 합격=%d, 불합격=%d",
                    sum(r.passed for r in reports),
                    sum(not r.passed for r in reports))

        # 4. 프로모션
        pack: PackResult | None = None
        passed_results  = [r for r, rp in zip(worker_results, reports) if rp.passed]
        passed_reports  = [rp for rp in reports if rp.passed]

        if passed_results:
            if output_path:
                pack = self._promoter.promote(
                    passed_results, passed_reports,
                    output_path=output_path,
                    mission_id=mission.mission_id,
                )
            else:
                _, pack = self._promoter.promote_to_bytes(
                    passed_results, passed_reports,
                    mission_id=mission.mission_id,
                )
            logger.info("Pack 생성 완료: %s (%d개)", pack.path, pack.included_count)

        return HarnessResult(
            mission_id     = mission.mission_id,
            jobs           = jobs,
            worker_results = worker_results,
            reports        = reports,
            pack           = pack,
            errors         = errors,
        )
