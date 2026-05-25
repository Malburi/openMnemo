"""
my-mcp 통합 테스트 러너.

모든 테스트 모듈을 순서대로 실행하고 결과를 요약합니다.

실행:
    cd C:/AI_Lab/my-mcp
    python -X utf8 scripts/test_all.py
"""

from __future__ import annotations

import importlib
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv(".env")
except ImportError:
    pass

# ── 테스트 모듈 목록 (실행 순서) ─────────────────────────────────────────────

_SUITES = [
    ("Week 3 — MCP Phase 1 (8 tools)",   "scripts.test_mcp"),
    ("Week 4 — CrabHarness",              "scripts.test_harness"),
    ("Week 5 — MCP Phase 2 (10 tools)",   "scripts.test_phase2"),
]


def _run_module(module_path: str) -> tuple[bool, float, str]:
    """모듈의 __main__ 블록을 직접 실행. (pass/fail, elapsed, error_msg)"""
    start = time.monotonic()
    try:
        mod = importlib.import_module(module_path)
        # 각 모듈의 테스트 함수를 직접 호출
        fns = [
            v for k, v in vars(mod).items()
            if k.startswith("test_") and callable(v)
        ]
        for fn in fns:
            fn()
        return True, time.monotonic() - start, ""
    except Exception:
        return False, time.monotonic() - start, traceback.format_exc()


# ── 러너 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("\n" + "=" * 60)
    print("  my-mcp 통합 테스트 러너")
    print("=" * 60)

    results: list[tuple[str, bool, float, str]] = []

    for label, module_path in _SUITES:
        print(f"\n▶  {label}")
        ok, elapsed, err = _run_module(module_path)
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"   {status}  ({elapsed:.2f}s)")
        if err:
            # 첫 5줄만 출력
            lines = err.strip().splitlines()
            for line in lines[-6:]:
                print(f"   {line}")
        results.append((label, ok, elapsed, err))

    # ── 요약 ──────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  결과 요약")
    print("=" * 60)
    passed = sum(1 for _, ok, _, _ in results if ok)
    failed = len(results) - passed
    total_time = sum(e for _, _, e, _ in results)

    for label, ok, elapsed, _ in results:
        mark = "✅" if ok else "❌"
        print(f"  {mark}  {label:<42}  {elapsed:.2f}s")

    print(f"\n  통과: {passed}/{len(results)}  총 시간: {total_time:.2f}s")
    print("=" * 60 + "\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
