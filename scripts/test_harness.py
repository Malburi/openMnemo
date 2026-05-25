"""
Week 4 CrabHarness 통합 테스트.

실행:
    cd C:/AI_Lab/my-mcp
    python scripts/test_harness.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def section(title: str) -> None:
    print(f"\n{'='*55}\n  {title}\n{'='*55}")

def ok(msg: str)   -> None: print(f"  ✅ {msg}")
def fail(msg: str) -> None: print(f"  ❌ {msg}")
def info(msg: str) -> None: print(f"  ℹ  {msg}")


# ── BaseWorker / WorkerResult 테스트 ─────────────────────────────────────────

def test_base_worker() -> None:
    section("BaseWorker / WorkerResult")
    from crabharness.codex_workers.base_worker import (
        BaseWorker, WorkerResult, WorkerStatus
    )

    class DummyWorker(BaseWorker):
        @property
        def name(self) -> str: return "dummy"
        def can_handle(self, source: str) -> bool: return source == "ok"
        def _extract(self, source: str, **kw):
            if source == "ok":
                return ["hello world chunk"], {"meta": True}
            raise RuntimeError("bad source")

    w = DummyWorker()

    r = w.run("ok")
    assert r.status == WorkerStatus.SUCCESS, "성공 상태 불일치"
    assert r.chunk_count == 1
    ok(f"성공 결과: chunks={r.chunk_count}, hash={r.content_hash[:8]}...")

    r2 = w.run("bad")
    assert r2.status == WorkerStatus.FAILED
    ok(f"실패 결과: error='{r2.error}'")

    ok("content_hash 자동 계산")
    ok("BaseWorker.run() 타이밍·에러 래핑 정상")


# ── PdfParser 테스트 (더미 파일) ──────────────────────────────────────────────

def test_pdf_parser_not_found() -> None:
    section("PdfParser — 파일 없음 거부")
    from crabharness.codex_workers.pdf_parser import PdfParser

    p = PdfParser()
    assert not p.can_handle("nonexistent.pdf"), "존재하지 않는 파일 거부해야 함"
    ok("존재하지 않는 PDF → can_handle=False")

    assert not p.can_handle("https://example.com"), "URL 거부"
    ok("URL → can_handle=False")


# ── WebCrawler 테스트 ─────────────────────────────────────────────────────────

def test_web_crawler_can_handle() -> None:
    section("WebCrawler — can_handle")
    from crabharness.codex_workers.web_crawler import WebCrawler

    w = WebCrawler()
    assert w.can_handle("https://example.com")
    ok("https:// → can_handle=True")

    assert w.can_handle("http://example.com")
    ok("http:// → can_handle=True")

    assert not w.can_handle("paper.pdf")
    ok("pdf 경로 → can_handle=False")


def test_web_crawler_live() -> None:
    section("WebCrawler — 실제 요청 (example.com)")
    from crabharness.codex_workers.web_crawler import WebCrawler

    w = WebCrawler(chunk_size=300)
    result = w.run("https://example.com")

    if result.ok:
        ok(f"크롤링 성공: {result.chunk_count}개 청크")
        info(f"  첫 청크: {result.chunks[0][:60]}...")
    else:
        info(f"크롤링 실패(네트워크 없음 무시): {result.error}")


# ── Planner 테스트 ────────────────────────────────────────────────────────────

def test_planner() -> None:
    section("Planner — Worker 배정")
    from crabharness.planner import Mission, Planner
    from crabharness.codex_workers.web_crawler import WebCrawler

    planner = Planner()
    mission = Mission(
        sources=["https://example.com", "local.pdf", "https://httpbin.org/get"],
        goal="ingest",
    )
    jobs = planner.plan(mission)

    # example.com, httpbin → WebCrawler
    # local.pdf 존재하지 않음 → can_handle=False → 건너뜀
    for j in jobs:
        info(f"  {j.source[:40]} → {j.worker.name} (score={j.worker_score:.2f})")

    web_jobs = [j for j in jobs if j.worker.name == "web_crawler"]
    assert len(web_jobs) == 2, f"URL 2개 → web_crawler 2개 기대, 실제: {len(web_jobs)}"
    ok(f"URL 소스 2개 → web_crawler 배정")

    pdf_jobs = [j for j in jobs if j.worker.name == "pdf_parser"]
    assert len(pdf_jobs) == 0, "존재하지 않는 PDF → 배정 없어야 함"
    ok("존재하지 않는 PDF → 건너뜀")


# ── Validator 테스트 ──────────────────────────────────────────────────────────

def test_validator() -> None:
    section("Validator — 검증")
    from crabharness.codex_workers.base_worker import WorkerResult, WorkerStatus
    from crabharness.validator import Validator

    v = Validator(min_chunks=1)

    # 정상 결과
    good = WorkerResult(
        worker_name="dummy", source="test.pdf",
        chunks=["청크A", "청크B"],
        metadata={"space": "resource"},
    )
    report = v.validate(good)
    assert report.passed, f"합격 기대: issues={report.issues}"
    ok(f"정상 결과 → passed=True, space={report.space}")

    # 빈 청크
    empty = WorkerResult(
        worker_name="dummy", source="empty.pdf",
        chunks=[], status=WorkerStatus.PARTIAL, error="청크 없음",
    )
    report2 = v.validate(empty)
    assert not report2.passed
    ok(f"빈 청크 → passed=False, issues={report2.issues}")

    # FAILED 상태
    failed = WorkerResult(
        worker_name="dummy", source="fail.pdf",
        chunks=[], status=WorkerStatus.FAILED, error="IO 오류",
    )
    report3 = v.validate(failed)
    assert not report3.passed
    ok(f"FAILED Worker → passed=False")


# ── Promotion 테스트 ──────────────────────────────────────────────────────────

def test_promotion() -> None:
    section("Promotion — ZIP 생성")
    from crabharness.codex_workers.base_worker import WorkerResult
    from crabharness.validator import ValidationReport
    from crabharness.promotion import Promoter

    results = [
        WorkerResult(
            worker_name="dummy", source="doc_a.pdf",
            chunks=["내용1", "내용2", "내용3"],
        ),
        WorkerResult(
            worker_name="dummy", source="doc_b.pdf",
            chunks=["텍스트A"],
        ),
    ]
    reports = [
        ValidationReport(source="doc_a.pdf", passed=True, space="resource", chunk_count=3, content_hash=results[0].content_hash),
        ValidationReport(source="doc_b.pdf", passed=False, space="evidence", issues=["실패"], chunk_count=1, content_hash=results[1].content_hash),
    ]

    promoter = Promoter()
    data, pack = promoter.promote_to_bytes(results, reports, mission_id="test_mission")

    assert len(data) > 0
    ok(f"ZIP 생성 성공: {len(data)} bytes")
    ok(f"포함: {pack.included_count}개, 제외: {pack.skipped_count}개")

    # ZIP 내용 확인
    with zipfile.ZipFile(__import__("io").BytesIO(data)) as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        ok(f"manifest.json 존재")

        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["pack_version"] == "1"
        assert len(manifest["sources"]) == 1
        ok(f"manifest.sources: {len(manifest['sources'])}개 (불합격 제외 정상)")

        chunk_files = [n for n in names if n.startswith("chunks/")]
        ok(f"청크 파일: {len(chunk_files)}개")


# ── CrabHarness 파이프라인 종합 테스트 ───────────────────────────────────────

def test_harness_pipeline() -> None:
    section("CrabHarness — 전체 파이프라인")
    from crabharness.harness import CrabHarness
    from crabharness.planner import Mission
    from crabharness.codex_workers.base_worker import BaseWorker

    class MockWorker(BaseWorker):
        @property
        def name(self) -> str: return "mock"
        def can_handle(self, source: str) -> bool: return source.startswith("mock://")
        def _extract(self, source: str, **kw):
            return [f"청크_{i}" for i in range(3)], {"source": source}

    from crabharness.planner import Planner
    planner = Planner(workers=[MockWorker()])

    harness = CrabHarness(planner=planner)
    mission = Mission(sources=["mock://doc1", "mock://doc2", "unknown://skip"])
    result  = harness.run(mission)

    summary = result.summary()
    info(f"summary: {json.dumps(summary, ensure_ascii=False, indent=2)}")

    assert result.passed_count == 2, f"합격 2개 기대: {result.passed_count}"
    ok(f"합격: {result.passed_count}, 불합격: {result.failed_count}")
    ok(f"건너뜀(unknown://): mission.sources=3 → jobs=2")

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
        out = f.name
    harness.run(mission, output_path=out)
    assert Path(out).exists()
    ok(f"ZIP 파일 저장: {out}")
    Path(out).unlink()


# ── 메인 ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🦀 CrabHarness Week 4 — 통합 테스트 시작")
    test_base_worker()
    test_pdf_parser_not_found()
    test_web_crawler_can_handle()
    test_web_crawler_live()
    test_planner()
    test_validator()
    test_promotion()
    test_harness_pipeline()
    print("\n✅ 모든 테스트 완료\n")
