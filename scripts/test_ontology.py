"""
Week 2 통합 테스트 — OntologyBuilder → HybridQuery → IdentityEngine 흐름.

실행:
    cd C:/AI_Lab/my-mcp
    python scripts/test_ontology.py
"""

import os
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


# ── normalize 테스트 (의존성 없음) ──────────────────────────────────────────

def test_normalize() -> None:
    section("Normalize 유틸")
    from openmnemo.ontology.normalize import (
        normalize_node_id, clean_text, split_text_to_chunks, merge_properties
    )

    cases = [
        ("GPT-4o",                          "gpt_4o"),
        ("Retrieval-Augmented Generation",  "retrieval_augmented_generation"),
        ("My API (v2)",                     "my_api_v2"),
    ]
    for raw, expected in cases:
        result = normalize_node_id(raw)
        if result == expected:
            ok(f"normalize_node_id('{raw}') → '{result}'")
        else:
            fail(f"normalize_node_id('{raw}') 기대={expected}, 실제={result}")

    chunks = split_text_to_chunks("가나다" * 200, chunk_size=100, chunk_overlap=20)
    ok(f"split_text_to_chunks: {len(chunks)}개 청크 생성")

    merged = merge_properties({"a": 1, "b": 2}, {"b": 99, "c": 3})
    ok(f"merge_properties: {merged}")

    cleaned = clean_text("hello\x00world  test")
    ok(f"clean_text: '{cleaned}'")


# ── OntologyBuilder 테스트 ──────────────────────────────────────────────────

def test_builder() -> None:
    section("OntologyBuilder (SQL만 사용)")
    from openmnemo.stores.sql_store import SQLStore
    from openmnemo.ontology.builder import OntologyBuilder

    sql = SQLStore(url="sqlite:///./test_builder.db")
    builder = OntologyBuilder(sql=sql)

    # 노드 추가
    r1 = builder.add_node("concept", "rag", properties={"label": "RAG"})
    ok(f"add_node concept/rag → receipt={r1[:8]}...")

    r2 = builder.add_node("resource", "paper_001", node_type="document",
                          properties={"title": "RAG 논문"})
    ok(f"add_node resource/paper_001 → receipt={r2[:8]}...")

    # 엣지 추가
    r3 = builder.add_edge("concept", "rag", "resource", "paper_001", "described_in")
    ok(f"add_edge concept/rag -[described_in]-> resource/paper_001 → receipt={r3[:8]}...")

    # 잘못된 관계 거부 확인
    try:
        builder.add_edge("concept", "rag", "resource", "paper_001", "invalid_rel")
        fail("잘못된 관계가 거부되지 않음")
    except ValueError as e:
        ok(f"잘못된 관계 거부 확인: {str(e)[:60]}")

    # 일괄 처리
    receipts = builder.add_nodes_bulk([
        {"space": "concept", "node_id": "embedding", "properties": {"label": "임베딩"}},
        {"space": "concept", "node_id": "vector_db", "properties": {"label": "벡터DB"}},
    ])
    ok(f"add_nodes_bulk: {len(receipts)}개 완료")

    # 통계
    stats = builder.stats()
    info(f"stats: {stats}")

    # 정리
    Path("./test_builder.db").unlink(missing_ok=True)
    ok("테스트 DB 삭제 완료")


# ── HybridQuery 테스트 ──────────────────────────────────────────────────────

def test_query() -> None:
    section("HybridQuery (ChromaDB 로컬)")
    from openmnemo.stores.chroma_store import ChromaStore
    from openmnemo.ontology.query import HybridQuery

    chroma = ChromaStore(collection="test_query", path="./.chroma_test")
    if not chroma.ping():
        fail("ChromaDB 사용 불가 — 스킵")
        return
    ok("ChromaDB ping 성공")

    engine = HybridQuery(chroma=chroma)

    # 수집
    ids = engine.ingest(
        texts=[
            "RAG는 검색 증강 생성(Retrieval-Augmented Generation) 기법입니다.",
            "임베딩은 텍스트를 고차원 벡터로 변환하는 과정입니다.",
            "pgvector는 PostgreSQL의 벡터 저장 확장입니다.",
            "Neo4j는 그래프 데이터베이스입니다.",
            "ChromaDB는 임베딩 벡터를 저장하는 벡터 DB입니다.",
        ],
        metadatas=[
            {"space": "concept", "node_id": "rag"},
            {"space": "concept", "node_id": "embedding"},
            {"space": "resource", "node_id": "pgvector"},
            {"space": "resource", "node_id": "neo4j"},
            {"space": "resource", "node_id": "chromadb"},
        ],
    )
    ok(f"ingest: {len(ids)}개 저장")

    # 일반 쿼리
    results = engine.query("벡터 저장 방법", top_k=3)
    ok(f"query('벡터 저장 방법') → {len(results)}건")
    for r in results:
        info(f"  [{r.source}] score={r.score:.3f} | {r.text[:50]}")

    # 관계형 쿼리 (그래프 확장 트리거 확인)
    is_rel = engine._is_relational_query("RAG와 임베딩의 관계는?")
    ok(f"관계형 쿼리 감지: {is_rel}")

    # 정리
    chroma.reset_collection()
    ok("ChromaDB 컬렉션 초기화 완료")


# ── IdentityEngine 테스트 ────────────────────────────────────────────────────

def test_identity() -> None:
    section("IdentityEngine")
    from openmnemo.stores.sql_store import SQLStore
    from openmnemo.ontology.identity import IdentityEngine

    sql = SQLStore(url="sqlite:///./test_identity.db")
    engine = IdentityEngine(sql=sql)

    # 별칭 등록
    engine.add_alias("rag", "retrieval_augmented_generation")
    engine.add_alias("rag", "rag_system")
    ok("add_alias 2개 등록")

    # 정규 ID 조회
    canonical = engine.resolve_canonical("retrieval_augmented_generation")
    ok(f"resolve_canonical: '{canonical}'") if canonical == "rag" else fail(f"기대=rag, 실제={canonical}")

    # 없는 별칭
    none_result = engine.resolve_canonical("nonexistent")
    ok(f"없는 별칭 → None: {none_result is None}")

    # 별칭 목록
    aliases = engine.list_aliases("rag")
    ok(f"list_aliases('rag'): {aliases}")

    # 중복 후보 제안
    cid = engine.propose_duplicate("rag", "rag_system", reason="이름 유사")
    ok(f"propose_duplicate → candidate_id={cid[:8]}...")

    # 대기 목록
    pending = engine.list_pending_duplicates()
    ok(f"list_pending_duplicates: {len(pending)}건")

    # 승인
    ok_resolve = engine.resolve_duplicate(cid, "approve")
    ok(f"resolve_duplicate(approve): {ok_resolve}")

    # 승인 후 대기 목록 확인
    pending_after = engine.list_pending_duplicates()
    ok(f"승인 후 대기 목록: {len(pending_after)}건 (0이어야 함)") if len(pending_after) == 0 \
        else fail(f"대기 목록이 비워지지 않음: {len(pending_after)}건")

    # 별칭 검색
    found = engine.find_duplicates_by_name("rag")
    ok(f"find_duplicates_by_name('rag'): {len(found)}건")

    # 정리
    Path("./test_identity.db").unlink(missing_ok=True)
    ok("테스트 DB 삭제 완료")


# ── 메인 ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🦀 my-mcp Week 2 — Ontology 통합 테스트 시작")
    test_normalize()
    test_builder()
    test_query()
    test_identity()
    print("\n✅ 테스트 완료\n")
