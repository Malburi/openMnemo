"""
Week 1 스토어 연결 및 기본 동작 테스트 스크립트.

실행:
    cd C:/AI_Lab/my-mcp
    python scripts/test_stores.py
"""

import os
import sys
from pathlib import Path

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(".env")

# ── 헬퍼 ────────────────────────────────────────────────────────────────────

def section(title: str) -> None:
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")

def ok(msg: str) -> None:
    print(f"  ✅ {msg}")

def fail(msg: str) -> None:
    print(f"  ❌ {msg}")

def info(msg: str) -> None:
    print(f"  ℹ  {msg}")


# ── grammar 테스트 ──────────────────────────────────────────────────────────

def test_grammar() -> None:
    section("Grammar / Validator")
    from openmnemo.grammar import validate_node, validate_edge, full_glossary

    r = validate_node("concept", "entity")
    ok("validate_node('concept', 'entity')") if r else fail(r.error)

    r = validate_node("concept", "invalid_type")
    ok(f"잘못된 노드 타입 거부: {r.error}") if not r else fail("거부 안 됨")

    r = validate_edge("subject", "resource", "owns")
    ok("validate_edge('subject', 'resource', 'owns')") if r else fail(r.error)

    r = validate_edge("subject", "resource", "invalid_rel")
    ok(f"잘못된 관계 거부: {r.error}") if not r else fail("거부 안 됨")

    glossary = full_glossary()
    info(f"공간 수: {len(glossary['spaces'])}, 관계 쌍 수: {len(glossary['relations'])}")


# ── ChromaDB 테스트 ─────────────────────────────────────────────────────────

def test_chroma() -> None:
    section("ChromaDB Store")
    from openmnemo.stores import ChromaStore

    store = ChromaStore(collection="test_ontology", path="./.chroma_test")

    if not store.ping():
        fail("ChromaDB 연결 실패 — 스킵")
        return
    ok("ping 성공")

    ids = store.upsert_texts(
        texts=["RAG는 검색 증강 생성 기법입니다.", "임베딩은 텍스트를 벡터로 변환합니다."],
        metadatas=[{"space": "concept"}, {"space": "concept"}],
    )
    ok(f"upsert_texts: {ids}")

    results = store.query("검색 기법", top_k=2)
    ok(f"query 결과 {len(results)}건: {[r['document'][:30] for r in results]}")

    store.delete(ids)
    ok("delete 완료")
    store.reset_collection()


# ── MongoDB 테스트 ──────────────────────────────────────────────────────────

def test_mongo() -> None:
    section("MongoDB Store")
    from openmnemo.stores import MongoStore

    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    store = MongoStore(uri=uri, db_name="my_mcp_test")

    if not store.ping():
        fail("MongoDB 연결 실패 — 스킵")
        return
    ok("ping 성공")

    doc = store.upsert_node_doc(
        space="concept", node_id="rag_test",
        node_type="entity", properties={"label": "RAG", "desc": "테스트"}
    )
    ok(f"upsert_node_doc: node_id={doc['node_id']}")

    fetched = store.get_node_doc("concept", "rag_test")
    ok(f"get_node_doc: {fetched['properties']}")

    store.log_event("test_event", {"msg": "테스트 로그"})
    ok("log_event 완료")

    stats = store.collection_stats()
    info(f"컬렉션 통계: {stats}")

    store.delete_node_doc("concept", "rag_test")
    ok("delete_node_doc 완료")
    store.close()


# ── SQL 테스트 ──────────────────────────────────────────────────────────────

def test_sql() -> None:
    section("SQL Store (SQLite)")
    from openmnemo.stores import SQLStore

    store = SQLStore(url="sqlite:///./test_my_mcp.db")

    if not store.ping():
        fail("SQL 연결 실패 — 스킵")
        return
    ok("ping 성공")

    store.register_node("concept", "entity", "rag_test")
    ok("register_node 완료")

    store.register_edge("concept", "rag_test", "resource", "paper_001", "described_in")
    ok("register_edge 완료")

    store.upsert_policy("user_001", "resource_001", "can_view")
    ok("upsert_policy 완료")

    allowed = store.check_policy("user_001", "resource_001", "can_view")
    ok(f"check_policy: {allowed}")

    denied = store.check_policy("user_001", "resource_001", "can_edit")
    ok(f"check_policy 거부 확인: {not denied}")

    run_id = store.create_run("index_document", {"file": "test.pdf"})
    ok(f"create_run: {run_id}")

    store.advance_run(run_id, "running", "처리 시작")
    store.advance_run(run_id, "completed", "완료")
    log = store.get_action_log(run_id)
    ok(f"워크플로우 이력 {len(log)}건: {[l['status'] for l in log]}")

    counts = store.table_counts()
    info(f"테이블 통계: {counts}")

    # 테스트 DB 삭제
    Path("./test_my_mcp.db").unlink(missing_ok=True)
    ok("테스트 DB 삭제 완료")


# ── Neo4j 테스트 ────────────────────────────────────────────────────────────

def test_neo4j() -> None:
    section("Neo4j Store")
    from openmnemo.stores import Neo4jStore

    uri  = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER",     "neo4j")
    pwd  = os.getenv("NEO4J_PASSWORD", "password")

    store = Neo4jStore(uri=uri, user=user, password=pwd)

    if not store.ping():
        fail("Neo4j 연결 실패 — 스킵 (Neo4j가 실행 중인지 확인하세요)")
        return
    ok("ping 성공")

    node = store.upsert_node(
        space="concept", node_type="entity", node_id="rag_test",
        properties={"label": "RAG", "description": "검색 증강 생성"}
    )
    ok(f"upsert_node: {node.get('node_id')}")

    fetched = store.get_node("concept", "rag_test")
    ok(f"get_node: {fetched}")

    store.upsert_node(space="resource", node_type="document", node_id="paper_001")
    store.upsert_edge("concept", "rag_test", "resource", "paper_001", "described_in")
    ok("upsert_edge 완료")

    count = store.count_nodes("concept")
    info(f"concept 공간 노드 수: {count}")

    store.delete_node("concept", "rag_test")
    store.delete_node("resource", "paper_001")
    ok("delete_node 완료")
    store.close()


# ── 메인 ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🦀 my-mcp Week 1 — Stores 테스트 시작")
    test_grammar()
    test_chroma()
    test_mongo()
    test_sql()
    test_neo4j()
    print("\n✅ 테스트 완료\n")
