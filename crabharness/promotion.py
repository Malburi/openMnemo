"""검증된 WorkerResult → OpenCrab Pack v1 ZIP 내보내기."""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from crabharness.codex_workers.base_worker import WorkerResult
from crabharness.validator import ValidationReport

_PACK_VERSION = "1"
_MANIFEST_FILE = "manifest.json"


@dataclass
class PackResult:
    path: str
    manifest: dict[str, Any]
    included_count: int
    skipped_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "path":           self.path,
            "pack_version":   _PACK_VERSION,
            "included_count": self.included_count,
            "skipped_count":  self.skipped_count,
            "manifest":       self.manifest,
        }


class Promoter:
    """
    ValidationReport 합격 결과만 ZIP으로 묶어 저장합니다.

    ZIP 구조:
        manifest.json          ← Pack 메타데이터
        chunks/<source_slug>/  ← 소스별 청크 텍스트 파일
            chunk_000.txt
            chunk_001.txt
            ...
        meta/<source_slug>.json  ← 소스별 메타데이터
    """

    def promote(
        self,
        results: list[WorkerResult],
        reports: list[ValidationReport],
        output_path: str,
        mission_id: str = "unknown",
    ) -> PackResult:
        passed = [
            (r, rp) for r, rp in zip(results, reports) if rp.passed
        ]
        skipped = len(results) - len(passed)

        manifest = _build_manifest(mission_id, passed)

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(_MANIFEST_FILE, json.dumps(manifest, ensure_ascii=False, indent=2))

            for result, report in passed:
                slug = _slugify(result.source)

                # 청크 파일
                for i, chunk in enumerate(result.chunks):
                    zf.writestr(f"chunks/{slug}/chunk_{i:04d}.txt", chunk)

                # 소스 메타데이터
                meta = {
                    **result.metadata,
                    "space":        report.space,
                    "worker":       result.worker_name,
                    "chunk_count":  result.chunk_count,
                    "content_hash": result.content_hash,
                    "elapsed_sec":  result.elapsed_sec,
                }
                zf.writestr(
                    f"meta/{slug}.json",
                    json.dumps(meta, ensure_ascii=False, indent=2),
                )

        return PackResult(
            path           = output_path,
            manifest       = manifest,
            included_count = len(passed),
            skipped_count  = skipped,
        )

    def promote_to_bytes(
        self,
        results: list[WorkerResult],
        reports: list[ValidationReport],
        mission_id: str = "unknown",
    ) -> tuple[bytes, PackResult]:
        """파일 저장 없이 ZIP을 바이트로 반환 (테스트·API용)."""
        passed  = [(r, rp) for r, rp in zip(results, reports) if rp.passed]
        skipped = len(results) - len(passed)
        manifest = _build_manifest(mission_id, passed)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(_MANIFEST_FILE, json.dumps(manifest, ensure_ascii=False, indent=2))
            for result, report in passed:
                slug = _slugify(result.source)
                for i, chunk in enumerate(result.chunks):
                    zf.writestr(f"chunks/{slug}/chunk_{i:04d}.txt", chunk)
                meta = {
                    **result.metadata,
                    "space":       report.space,
                    "worker":      result.worker_name,
                    "chunk_count": result.chunk_count,
                }
                zf.writestr(f"meta/{slug}.json", json.dumps(meta, ensure_ascii=False, indent=2))

        return buf.getvalue(), PackResult(
            path           = "<in-memory>",
            manifest       = manifest,
            included_count = len(passed),
            skipped_count  = skipped,
        )


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _build_manifest(
    mission_id: str,
    passed: list[tuple[WorkerResult, ValidationReport]],
) -> dict[str, Any]:
    return {
        "pack_version": _PACK_VERSION,
        "mission_id":   mission_id,
        "created_at":   datetime.now(tz=timezone.utc).isoformat(),
        "sources": [
            {
                "source":      r.source,
                "worker":      r.worker_name,
                "space":       rp.space,
                "chunk_count": r.chunk_count,
                "hash":        r.content_hash,
            }
            for r, rp in passed
        ],
    }


def _slugify(source: str) -> str:
    """소스 경로·URL을 파일시스템 안전한 슬러그로 변환."""
    import re
    slug = re.sub(r"[^\w\-]", "_", source)
    return slug[:80]
