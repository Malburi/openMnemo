"""
Week 5 Phase 2 MCP 도구 테스트 (10개 신규 도구).

실행:
    cd C:/AI_Lab/my-mcp
    python -X utf8 scripts/test_phase2.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv(".env")
except ImportError:
    pass


def section(title: str) -> None:
    print(f"\n{'='*55}\n  {title}\n{'='*55}")

def ok(msg: str)   -> None: print(f"  ✅ {msg}")
def fail(msg: str) -> None: print(f"  ❌ {msg}")
def info(msg: str) -> None: print(f"  ℹ  {msg}")


def call(server, method: str, params: dict | None = None) -> dict:
    req = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return server._dispatch(req)


def tool(server, name: str, **kwargs) -> dict:
    resp = call(server, "tools/call", {"name": name, "arguments": kwargs})
    return json.loads(resp["result"]["content"][0]["text"])


# ── tools/list Phase 2 확인 ───────────────────────────────────────────────────

def test_tools_list_phase2() -> None:
    section("tools/list — Phase 2 도구 포함 확인")
    from openmnemo.mcp.server import MCPServer
    server = MCPServer()
    resp = call(server, "tools/list")
    names = [t["name"] for t in resp["result"]["tools"]]
    info(f"전체 도구 수: {len(names)}")

    phase2 = [
        "identity_add_alias", "identity_resolve",
        "identity_propose_duplicate", "identity_resolve_duplicate",
        "workflow_create", "workflow_advance", "workflow_list",
        "impact_record", "impact_history", "harness_run",
    ]
    for n in phase2:
        if n in names:
            ok(f"도구 존재: {n}")
        else:
            fail(f"도구 없음: {n}")

    assert len(names) == 18, f"총 18개 도구 기대, 실제: {len(names)}"
    ok(f"총 도구 수: {len(names)} (Phase1=8 + Phase2=10)")


# ── Identity 테스트 ──────────────────────────────────────────────────────────

def test_identity() -> None:
    section("Identity 도구")
    from openmnemo.mcp.server import MCPServer
    server = MCPServer()

    # add_alias
    r = tool(server, "identity_add_alias",
             canonical_id="rag_system", alias="retrieval_augmented_generation", space="concept")
    ok(f"add_alias: {r['alias']} → {r['canonical_id']}")

    r2 = tool(server, "identity_add_alias",
              canonical_id="rag_system", alias="rag", space="concept")
    ok(f"add_alias 두 번째: {r2['alias']} → {r2['canonical_id']}")

    # resolve
    r3 = tool(server, "identity_resolve", alias="retrieval_augmented_generation")
    assert r3["found"], f"별칭 해석 실패: {r3}"
    assert r3["canonical_id"] == "rag_system"
    ok(f"resolve: '{r3['alias']}' → '{r3['canonical_id']}'")

    r4 = tool(server, "identity_resolve", alias="nonexistent_alias")
    assert not r4["found"]
    ok(f"resolve 없음: found=False")

    # propose_duplicate
    r5 = tool(server, "identity_propose_duplicate",
              node_a="rag_system", node_b="rag_pipeline",
              space="concept", reason="이름 유사")
    cid = r5["candidate_id"]
    ok(f"propose_duplicate: candidate_id={cid[:8]}...")

    # resolve_duplicate — approve
    r6 = tool(server, "identity_resolve_duplicate",
              candidate_id=cid, action="approve")
    assert r6["updated"]
    ok(f"resolve_duplicate approve: updated=True")

    # reject 같은 ID 다시 → 이미 처리됨 → updated=False
    r7 = tool(server, "identity_resolve_duplicate",
              candidate_id=cid, action="reject")
    assert not r7["updated"], "이미 approve된 항목 reject 불가"
    ok(f"이미 처리된 후보 재처리 거부: updated=False")


# ── Workflow 테스트 ──────────────────────────────────────────────────────────

def test_workflow() -> None:
    section("Workflow 도구")
    from openmnemo.mcp.server import MCPServer
    server = MCPServer()

    # create
    r = tool(server, "workflow_create",
             action_type="ingest", payload={"source": "test.pdf"})
    run_id = r["run_id"]
    assert r["status"] == "pending"
    ok(f"workflow_create: run_id={run_id[:8]}..., status={r['status']}")

    # advance → running
    r2 = tool(server, "workflow_advance",
              run_id=run_id, new_status="running", note="처리 시작", actor="test")
    assert r2["updated"]
    ok(f"workflow_advance → running: updated=True")

    # advance → completed
    r3 = tool(server, "workflow_advance",
              run_id=run_id, new_status="completed", note="완료")
    assert r3["updated"]
    ok(f"workflow_advance → completed: updated=True")

    # advance 없는 run_id
    r4 = tool(server, "workflow_advance",
              run_id="nonexistent-run-id", new_status="failed")
    assert not r4["updated"]
    ok(f"없는 run_id advance: updated=False")

    # list — 필터 없음
    r5 = tool(server, "workflow_list")
    assert r5["count"] >= 1
    ok(f"workflow_list: {r5['count']}개")

    # list — completed 필터
    r6 = tool(server, "workflow_list", status="completed", limit=5)
    ok(f"workflow_list status=completed: {r6['count']}개")
    for run in r6["runs"]:
        info(f"  {run['run_id'][:8]}... | {run['action_type']} | {run['status']}")


# ── Impact 테스트 ─────────────────────────────────────────────────────────────

def test_impact() -> None:
    section("Impact 도구")
    from openmnemo.mcp.server import MCPServer
    server = MCPServer()

    # record
    r = tool(server, "impact_record",
             node_id="rag_system", space="concept", category="I6",
             result={"description": "RAG 지식 생성 영향", "score": 0.85})
    assert r["recorded"]
    ok(f"impact_record: node_id={r['node_id']}, category={r['category']}")

    r2 = tool(server, "impact_record",
              node_id="rag_system", space="concept", category="I1",
              result={"changed_fields": ["description"]})
    ok(f"impact_record I1 데이터변화")

    # history
    r3 = tool(server, "impact_history", node_id="rag_system", limit=10)
    assert r3["count"] >= 2
    ok(f"impact_history: {r3['count']}건")
    for entry in r3["history"]:
        info(f"  [{entry['category']}] {entry['created_at'][:19]}")

    # 없는 노드 이력
    r4 = tool(server, "impact_history", node_id="nonexistent_node_xyz")
    assert r4["count"] == 0
    ok(f"없는 노드 이력: count=0")


# ── harness_run 테스트 (Mock Worker 활용) ────────────────────────────────────

def test_harness_run() -> None:
    section("harness_run 도구")
    from openmnemo.mcp.server import MCPServer
    from openmnemo.mcp.context import get_context

    server = MCPServer()

    # 존재하지 않는 소스만 넘기면 jobs=0
    r = tool(server, "harness_run",
             sources=["nonexistent.pdf", "not_a_url"],
             auto_ingest=False)
    ok(f"처리 불가 소스: total_sources={r['total_sources']}, passed={r['passed']}")

    # URL (네트워크 없으면 failed로 처리됨 — 에러 없이 완료)
    r2 = tool(server, "harness_run",
              sources=["https://example.com"],
              auto_ingest=False)
    info(f"URL 소스 결과: total={r2['total_sources']}, passed={r2['passed']}, failed={r2['failed']}")
    ok(f"harness_run URL 처리 완료 (네트워크 결과 무관하게 응답 정상)")


# ── 전체 도구 inputSchema 검증 ────────────────────────────────────────────────

def test_all_schemas() -> None:
    section("전체 18개 도구 inputSchema 검증")
    from openmnemo.mcp.server import MCPServer
    server = MCPServer()
    resp = call(server, "tools/list")
    tools_list = resp["result"]["tools"]

    for t in tools_list:
        assert "inputSchema" in t, f"{t['name']}: inputSchema 없음"
        assert "description" in t, f"{t['name']}: description 없음"
    ok(f"모든 {len(tools_list)}개 도구에 inputSchema·description 존재")


# ── 메인 ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🦀 Week 5 Phase 2 — MCP 도구 테스트 시작")
    test_tools_list_phase2()
    test_identity()
    test_workflow()
    test_impact()
    test_harness_run()
    test_all_schemas()
    print("\n✅ Phase 2 테스트 완료\n")
