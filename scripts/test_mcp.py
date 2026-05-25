"""
Week 3 MCP 서버 테스트 — JSON-RPC 흐름 직접 검증.

실행:
    cd C:/AI_Lab/my-mcp
    python scripts/test_mcp.py
"""

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
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"{'='*55}")

def ok(msg: str)   -> None: print(f"  ✅ {msg}")
def fail(msg: str) -> None: print(f"  ❌ {msg}")
def info(msg: str) -> None: print(f"  ℹ  {msg}")


# ── 서버 직접 호출 헬퍼 ──────────────────────────────────────────────────────

def call_server(server, method: str, params: dict | None = None, req_id: int = 1) -> dict | None:
    """MCPServer._dispatch()를 직접 호출해 네트워크 없이 테스트."""
    req = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params or {},
    }
    return server._dispatch(req)


# ── initialize 테스트 ────────────────────────────────────────────────────────

def test_initialize() -> None:
    section("initialize 핸드셰이크")
    from openmnemo.mcp.server import MCPServer

    server = MCPServer()
    resp = call_server(server, "initialize", {
        "protocolVersion": "2024-11-05",
        "clientInfo": {"name": "test-client", "version": "0.0.1"},
    })

    assert resp is not None, "응답이 없음"
    result = resp["result"]
    ok(f"protocolVersion: {result['protocolVersion']}")
    ok(f"serverInfo: {result['serverInfo']}")
    ok(f"capabilities: {result['capabilities']}")


# ── tools/list 테스트 ────────────────────────────────────────────────────────

def test_tools_list() -> None:
    section("tools/list")
    from openmnemo.mcp.server import MCPServer

    server = MCPServer()
    resp = call_server(server, "tools/list")

    tools = resp["result"]["tools"]
    names = [t["name"] for t in tools]
    ok(f"도구 수: {len(tools)}")
    info(f"도구 목록: {names}")

    required = [
        "ping", "ontology_manifest", "ontology_ingest",
        "ontology_add_node", "ontology_add_edge",
        "ontology_query", "query_bm25", "ontology_extract",
    ]
    for name in required:
        if name in names:
            ok(f"도구 존재: {name}")
        else:
            fail(f"도구 없음: {name}")

    # inputSchema 검증
    for tool in tools:
        assert "inputSchema" in tool, f"{tool['name']}: inputSchema 없음"
    ok("모든 도구에 inputSchema 존재")


# ── ping 도구 테스트 ─────────────────────────────────────────────────────────

def test_ping() -> None:
    section("ping 도구")
    from openmnemo.mcp.server import MCPServer

    server = MCPServer()
    resp = call_server(server, "tools/call", {"name": "ping", "arguments": {}})

    content = json.loads(resp["result"]["content"][0]["text"])
    ok(f"status: {content['status']}")
    info(f"stores: {content['stores']}")


# ── ontology_manifest 테스트 ─────────────────────────────────────────────────

def test_manifest() -> None:
    section("ontology_manifest 도구")
    from openmnemo.mcp.server import MCPServer

    server = MCPServer()
    resp = call_server(server, "tools/call", {"name": "ontology_manifest", "arguments": {}})

    content = json.loads(resp["result"]["content"][0]["text"])
    ok(f"공간 수: {len(content['spaces'])}")
    ok(f"관계 쌍 수: {len(content['relations'])}")
    info(f"공간 목록: {list(content['spaces'].keys())}")


# ── ontology_add_node + ontology_add_edge 테스트 ─────────────────────────────

def test_add_node_edge() -> None:
    section("ontology_add_node / ontology_add_edge")
    from openmnemo.mcp.server import MCPServer

    server = MCPServer()

    # 노드 추가
    resp = call_server(server, "tools/call", {
        "name": "ontology_add_node",
        "arguments": {
            "space": "concept",
            "node_id": "RAG System",
            "properties": {"label": "RAG", "description": "검색 증강 생성"},
        },
    })
    result = json.loads(resp["result"]["content"][0]["text"])
    if "error" not in result:
        ok(f"add_node: receipt={result['receipt_id'][:8]}..., node_id={result['node_id']}")
    else:
        fail(f"add_node 실패: {result['error']}")

    # 두 번째 노드
    call_server(server, "tools/call", {
        "name": "ontology_add_node",
        "arguments": {"space": "resource", "node_id": "paper_001", "node_type": "document"},
    })

    # 엣지 추가
    resp = call_server(server, "tools/call", {
        "name": "ontology_add_edge",
        "arguments": {
            "from_space": "concept",
            "from_id": "rag_system",
            "to_space": "resource",
            "to_id": "paper_001",
            "relation": "described_in",
        },
    })
    result = json.loads(resp["result"]["content"][0]["text"])
    if "error" not in result:
        ok(f"add_edge: receipt={result['receipt_id'][:8]}...")
    else:
        fail(f"add_edge 실패: {result['error']}")

    # 잘못된 관계 거부 확인
    resp = call_server(server, "tools/call", {
        "name": "ontology_add_edge",
        "arguments": {
            "from_space": "concept", "from_id": "rag_system",
            "to_space": "resource", "to_id": "paper_001",
            "relation": "invalid_relation",
        },
    })
    result = json.loads(resp["result"]["content"][0]["text"])
    ok(f"잘못된 관계 거부: {'error' in result}")


# ── ontology_ingest + ontology_query 테스트 ──────────────────────────────────

def test_ingest_query() -> None:
    section("ontology_ingest / ontology_query")
    from openmnemo.mcp.server import MCPServer
    from openmnemo.stores.chroma_store import ChromaStore

    chroma = ChromaStore(collection="test_mcp", path="./.chroma_test_mcp")
    if not chroma.ping():
        fail("ChromaDB 사용 불가 — 스킵")
        return
    ok("ChromaDB 사용 가능")

    server = MCPServer()
    # ChromaDB 컨텍스트 직접 주입
    from openmnemo.mcp.context import get_context
    ctx = get_context()
    ctx["chroma"] = chroma
    from openmnemo.ontology.query import HybridQuery
    ctx["query"] = HybridQuery(chroma=chroma)
    server._ctx = ctx

    # ingest
    resp = call_server(server, "tools/call", {
        "name": "ontology_ingest",
        "arguments": {
            "texts": [
                "RAG는 검색 증강 생성 기법입니다.",
                "pgvector는 PostgreSQL 벡터 확장입니다.",
                "ChromaDB는 로컬 벡터 DB입니다.",
            ],
        },
    })
    result = json.loads(resp["result"]["content"][0]["text"])
    ok(f"ingest: {result['ingested']}개 저장")

    # query
    resp = call_server(server, "tools/call", {
        "name": "ontology_query",
        "arguments": {"query": "벡터 저장소", "top_k": 3},
    })
    result = json.loads(resp["result"]["content"][0]["text"])
    ok(f"query: {result['count']}건")
    for r in result["results"]:
        info(f"  score={r['score']:.3f} | {r['text'][:50]}")

    chroma.reset_collection()
    ok("테스트 컬렉션 초기화 완료")


# ── 알 수 없는 메서드 에러 테스트 ────────────────────────────────────────────

def test_error_handling() -> None:
    section("에러 처리")
    from openmnemo.mcp.server import MCPServer

    server = MCPServer()

    # 알 수 없는 메서드
    resp = server._handle_raw(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "nonexistent"})
    )
    assert resp["error"]["code"] == -32601
    ok(f"알 수 없는 메서드 → code={resp['error']['code']}")

    # JSON 파싱 오류
    resp = server._handle_raw("this is not json")
    assert resp["error"]["code"] == -32700
    ok(f"JSON 파싱 오류 → code={resp['error']['code']}")

    # 알 수 없는 도구
    resp = call_server(server, "tools/call", {"name": "unknown_tool", "arguments": {}})
    result = json.loads(resp["result"]["content"][0]["text"])
    ok(f"알 수 없는 도구 → error: {'error' in result}")


# ── Claude Code .mcp.json 설정 안내 ─────────────────────────────────────────

def print_claude_config() -> None:
    section("Claude Code 연결 설정")
    config = {
        "mcpServers": {
            "my-mcp": {
                "command": "python",
                "args": ["-m", "openmnemo.mcp.server"],
                "cwd": str(Path(__file__).parent.parent),
                "env": {
                    "SQL_URL":         "sqlite:///./my_mcp.db",
                    "CHROMA_PATH":     "./.chroma",
                    "NEO4J_URI":       "bolt://localhost:7687",
                    "NEO4J_USER":      "neo4j",
                    "NEO4J_PASSWORD":  "your_password",
                },
            }
        }
    }
    print("\n  📄 .mcp.json (프로젝트 루트에 저장):")
    print("  " + json.dumps(config, ensure_ascii=False, indent=2).replace("\n", "\n  "))
    print()
    print("  또는 Claude Code CLI에서:")
    print("  $ claude mcp add my-mcp -- python -m openmnemo.mcp.server")
    print()


# ── 메인 ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🦀 my-mcp Week 3 — MCP 서버 테스트 시작")
    test_initialize()
    test_tools_list()
    test_ping()
    test_manifest()
    test_add_node_edge()
    test_ingest_query()
    test_error_handling()
    print_claude_config()
    print("✅ 테스트 완료\n")
