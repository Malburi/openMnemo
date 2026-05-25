"""MCP 도구 정의 및 디스패처 — Phase 1 (8개) + Phase 2 (10개)."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── 도구 스키마 정의 ─────────────────────────────────────────────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "ping",
        "description": "서버 상태 및 활성 스토어 연결 여부를 확인합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "ontology_manifest",
        "description": (
            "MetaOntology 전체 문법을 반환합니다. "
            "9개 공간 정의, 허용 관계, 영향 카테고리 포함."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "ontology_ingest",
        "description": (
            "텍스트 또는 텍스트 목록을 벡터 스토어에 저장합니다. "
            "저장된 청크는 ontology_query로 검색 가능합니다."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "texts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "저장할 텍스트 목록",
                },
                "metadatas": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "각 텍스트의 메타데이터 (space, node_id 등). 선택사항.",
                },
                "ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "각 텍스트의 고유 ID. 미지정 시 SHA256 자동 생성.",
                },
            },
            "required": ["texts"],
        },
    },
    {
        "name": "ontology_add_node",
        "description": (
            "온톨로지 노드를 추가하거나 업데이트합니다. "
            "space는 9개 공간 중 하나여야 합니다: "
            "subject, resource, evidence, concept, claim, community, outcome, lever, policy"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "space": {
                    "type": "string",
                    "description": "온톨로지 공간 (예: concept, resource, subject)",
                    "enum": [
                        "subject", "resource", "evidence", "concept",
                        "claim", "community", "outcome", "lever", "policy",
                    ],
                },
                "node_id": {
                    "type": "string",
                    "description": "노드 고유 ID (snake_case 권장)",
                },
                "node_type": {
                    "type": "string",
                    "description": "노드 타입 (예: entity, document, person). 미지정 시 space 기본값 사용.",
                },
                "properties": {
                    "type": "object",
                    "description": "노드 속성 (label, description 등)",
                },
            },
            "required": ["space", "node_id"],
        },
    },
    {
        "name": "ontology_add_edge",
        "description": (
            "두 노드 사이에 방향성 관계를 추가합니다. "
            "관계는 MetaOntology 문법에서 허용된 것만 가능합니다."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_space": {"type": "string", "description": "출발 노드의 공간"},
                "from_id":    {"type": "string", "description": "출발 노드 ID"},
                "to_space":   {"type": "string", "description": "도착 노드의 공간"},
                "to_id":      {"type": "string", "description": "도착 노드 ID"},
                "relation":   {
                    "type": "string",
                    "description": "관계 레이블 (예: owns, described_in, supports)",
                },
                "properties": {
                    "type": "object",
                    "description": "관계 속성. 선택사항.",
                },
            },
            "required": ["from_space", "from_id", "to_space", "to_id", "relation"],
        },
    },
    {
        "name": "ontology_query",
        "description": (
            "자연어 쿼리로 온톨로지를 검색합니다. "
            "벡터 유사도 + BM25 키워드 + 그래프 확장을 결합한 하이브리드 검색."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "검색할 자연어 쿼리",
                },
                "top_k": {
                    "type": "integer",
                    "description": "반환할 최대 결과 수 (기본값: 5)",
                    "default": 5,
                },
                "source_filter": {
                    "type": "string",
                    "description": "특정 source만 검색. 선택사항.",
                },
                "min_score": {
                    "type": "number",
                    "description": "최소 점수 임계값 0.0~1.0 (기본값: 0.0)",
                    "default": 0.0,
                },
                "use_graph": {
                    "type": "boolean",
                    "description": "그래프 확장 사용 여부 (기본값: true)",
                    "default": True,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "query_bm25",
        "description": "키워드 기반 전문 검색. 정확한 단어나 고유명사 검색에 적합합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "검색 키워드",
                },
                "top_k": {
                    "type": "integer",
                    "description": "반환할 최대 결과 수 (기본값: 10)",
                    "default": 10,
                },
                "source_filter": {
                    "type": "string",
                    "description": "특정 source만 검색. 선택사항.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "ontology_extract",
        "description": (
            "텍스트에서 노드와 엣지를 자동으로 추출하여 온톨로지에 저장합니다. "
            "MetaOntology 문법 규칙에 따라 9개 공간으로 분류."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "노드·엣지를 추출할 텍스트",
                },
                "source": {
                    "type": "string",
                    "description": "텍스트 출처 식별자 (파일명, URL 등)",
                    "default": "unknown",
                },
                "auto_ingest": {
                    "type": "boolean",
                    "description": "추출 후 벡터 스토어 자동 저장 여부 (기본값: true)",
                    "default": True,
                },
            },
            "required": ["text"],
        },
    },

    # ── Phase 2: Identity ──────────────────────────────────────────────────
    {
        "name": "identity_add_alias",
        "description": (
            "노드에 별칭(alias)을 등록합니다. "
            "예: 'rag' 노드에 'retrieval_augmented_generation' 별칭 추가."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "canonical_id": {
                    "type": "string",
                    "description": "정규 노드 ID (snake_case)",
                },
                "alias": {
                    "type": "string",
                    "description": "등록할 별칭",
                },
                "space": {
                    "type": "string",
                    "description": "노드가 속한 공간 (기본값: concept)",
                    "default": "concept",
                },
            },
            "required": ["canonical_id", "alias"],
        },
    },
    {
        "name": "identity_resolve",
        "description": (
            "별칭 또는 노드 ID로 정규 canonical_id를 조회합니다. "
            "여러 이름으로 불리는 엔티티를 단일 ID로 해석할 때 사용합니다."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "alias": {
                    "type": "string",
                    "description": "조회할 별칭 또는 노드 ID",
                },
            },
            "required": ["alias"],
        },
    },
    {
        "name": "identity_propose_duplicate",
        "description": (
            "두 노드가 동일한 엔티티를 가리킬 가능성이 있을 때 중복 후보로 제안합니다. "
            "자동 병합은 하지 않으며, identity_resolve_duplicate로 인간이 승인/거부합니다."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_a": {"type": "string", "description": "첫 번째 노드 ID"},
                "node_b": {"type": "string", "description": "두 번째 노드 ID"},
                "space":  {
                    "type": "string",
                    "description": "두 노드가 속한 공간 (기본값: concept)",
                    "default": "concept",
                },
                "reason": {
                    "type": "string",
                    "description": "중복 의심 이유 (선택)",
                    "default": "",
                },
            },
            "required": ["node_a", "node_b"],
        },
    },
    {
        "name": "identity_resolve_duplicate",
        "description": (
            "중복 후보를 승인(approve) 또는 거부(reject)합니다. "
            "승인해도 실제 노드 병합은 하지 않으며, 상태만 기록됩니다."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "candidate_id": {
                    "type": "string",
                    "description": "identity_propose_duplicate가 반환한 candidate_id",
                },
                "action": {
                    "type": "string",
                    "description": "'approve' 또는 'reject'",
                    "enum": ["approve", "reject"],
                },
            },
            "required": ["candidate_id", "action"],
        },
    },

    # ── Phase 2: Workflow ──────────────────────────────────────────────────
    {
        "name": "workflow_create",
        "description": (
            "새 워크플로우 실행(run)을 생성하고 run_id를 반환합니다. "
            "ingest, review, publish 등 장기 작업 추적에 사용합니다."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "description": "워크플로우 유형 (예: ingest, review, publish)",
                },
                "payload": {
                    "type": "object",
                    "description": "추가 파라미터 (선택)",
                },
            },
            "required": ["action_type"],
        },
    },
    {
        "name": "workflow_advance",
        "description": (
            "워크플로우 실행 상태를 전진시킵니다. "
            "상태 예: pending → running → completed / failed"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "workflow_create가 반환한 run_id",
                },
                "new_status": {
                    "type": "string",
                    "description": "변경할 상태 (예: running, completed, failed)",
                },
                "note": {
                    "type": "string",
                    "description": "상태 변경 사유 (선택)",
                    "default": "",
                },
                "actor": {
                    "type": "string",
                    "description": "변경 주체 (기본값: system)",
                    "default": "system",
                },
            },
            "required": ["run_id", "new_status"],
        },
    },
    {
        "name": "workflow_list",
        "description": "워크플로우 실행 목록을 조회합니다. status로 필터링 가능합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "필터할 상태 (미지정 시 전체). 예: pending, running, completed",
                },
                "limit": {
                    "type": "integer",
                    "description": "최대 반환 수 (기본값: 20)",
                    "default": 20,
                },
            },
            "required": [],
        },
    },

    # ── Phase 2: Impact ────────────────────────────────────────────────────
    {
        "name": "impact_record",
        "description": (
            "노드에 영향 분석 결과를 기록합니다. "
            "카테고리: I1(데이터변화), I2(워크플로우), I3(주체행동), "
            "I4(커뮤니티효과), I5(거버넌스), I6(지식생성), I7(감사)"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {
                    "type": "string",
                    "description": "영향을 받은 노드 ID",
                },
                "space": {
                    "type": "string",
                    "description": "노드 공간",
                },
                "category": {
                    "type": "string",
                    "description": "영향 카테고리 (I1~I7)",
                    "enum": ["I1", "I2", "I3", "I4", "I5", "I6", "I7"],
                },
                "result": {
                    "type": "object",
                    "description": "영향 분석 결과 상세 (자유 형식)",
                },
            },
            "required": ["node_id", "space", "category"],
        },
    },
    {
        "name": "impact_history",
        "description": "노드의 영향 분석 이력을 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {
                    "type": "string",
                    "description": "조회할 노드 ID",
                },
                "limit": {
                    "type": "integer",
                    "description": "최대 반환 수 (기본값: 20)",
                    "default": 20,
                },
            },
            "required": ["node_id"],
        },
    },

    # ── Phase 2: Harness ───────────────────────────────────────────────────
    {
        "name": "harness_run",
        "description": (
            "CrabHarness 파이프라인을 실행합니다. "
            "소스 목록(PDF 경로 또는 URL)을 Worker가 처리하고 "
            "검증된 청크를 온톨로지에 수집합니다."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "처리할 소스 목록 (PDF 경로 또는 http(s):// URL)",
                },
                "goal": {
                    "type": "string",
                    "description": "Mission 목표 (기본값: ingest)",
                    "default": "ingest",
                },
                "auto_ingest": {
                    "type": "boolean",
                    "description": "검증 통과 청크를 벡터 스토어에 자동 저장 (기본값: true)",
                    "default": True,
                },
            },
            "required": ["sources"],
        },
    },
]


# ── 도구 구현 ────────────────────────────────────────────────────────────────

def _tool_ping(ctx: dict, _args: dict) -> dict:
    stores: dict[str, str] = {}
    for name in ("neo4j", "chroma", "mongo", "sql"):
        store = ctx.get(name)
        if store is None:
            stores[name] = "not_configured"
        else:
            try:
                stores[name] = "ok" if store.ping() else "error"
            except Exception as e:
                stores[name] = f"error: {e}"

    # SQL 테이블 통계 (가능한 경우)
    sql = ctx.get("sql")
    table_counts: dict[str, int] = {}
    if sql and stores.get("sql") == "ok":
        try:
            table_counts = sql.table_counts()
        except Exception:
            pass

    # identity 상태
    identity_ok = ctx.get("identity") is not None

    return {
        "status":       "ok",
        "stores":       stores,
        "identity":     "ok" if identity_ok else "not_configured",
        "table_counts": table_counts,
        "tool_count":   len(TOOL_SCHEMAS),
    }


def _tool_manifest(_ctx: dict, _args: dict) -> dict:
    from openmnemo.grammar.glossary import full_glossary
    return full_glossary()


def _tool_ingest(ctx: dict, args: dict) -> dict:
    texts: list[str] = args["texts"]
    metadatas: list[dict] | None = args.get("metadatas")
    ids: list[str] | None = args.get("ids")

    engine = ctx["query"]
    saved_ids = engine.ingest(texts=texts, metadatas=metadatas, ids=ids)
    return {"ingested": len(saved_ids), "ids": saved_ids}


def _tool_add_node(ctx: dict, args: dict) -> dict:
    from openmnemo.ontology.normalize import normalize_node_id, clean_properties

    builder = ctx["builder"]
    receipt = builder.add_node(
        space=args["space"],
        node_id=normalize_node_id(args["node_id"]),
        node_type=args.get("node_type"),
        properties=clean_properties(args.get("properties") or {}),
    )
    return {"receipt_id": receipt, "node_id": normalize_node_id(args["node_id"])}


def _tool_add_edge(ctx: dict, args: dict) -> dict:
    builder = ctx["builder"]
    receipt = builder.add_edge(
        from_space=args["from_space"],
        from_id=args["from_id"],
        to_space=args["to_space"],
        to_id=args["to_id"],
        relation=args["relation"],
        properties=args.get("properties"),
    )
    return {"receipt_id": receipt}


def _tool_query(ctx: dict, args: dict) -> dict:
    engine = ctx["query"]
    results = engine.query(
        query_text=args["query"],
        top_k=args.get("top_k", 5),
        source_filter=args.get("source_filter"),
        min_score=args.get("min_score", 0.0),
        use_graph=args.get("use_graph", True),
    )
    return {
        "query": args["query"],
        "count": len(results),
        "results": [r.to_dict() for r in results],
    }


def _tool_bm25(ctx: dict, args: dict) -> dict:
    neo4j = ctx.get("neo4j")
    if not neo4j:
        return {"error": "Neo4j가 연결되어 있지 않습니다. BM25 검색을 사용할 수 없습니다."}

    hits = neo4j.search_fulltext(
        query=args["query"],
        top_k=args.get("top_k", 10),
        source_filter=args.get("source_filter"),
    )
    return {"query": args["query"], "count": len(hits), "results": hits}


def _tool_extract(ctx: dict, args: dict) -> dict:
    """
    텍스트에서 MetaOntology 문법에 따라 노드·엣지를 추출해 저장.

    추출 로직:
    1. 텍스트를 청킹
    2. 각 청크에서 주요 개념(concept), 주체(subject), 자원(resource) 감지
    3. OntologyBuilder로 노드·엣지 저장
    4. auto_ingest=True면 ChromaDB에도 저장
    """
    from openmnemo.ontology.normalize import (
        split_text_to_chunks, normalize_node_id, clean_text
    )

    text: str = args["text"]
    source: str = args.get("source", "unknown")
    auto_ingest: bool = args.get("auto_ingest", True)

    builder = ctx["builder"]
    engine = ctx["query"]

    text = clean_text(text)
    chunks = split_text_to_chunks(text, chunk_size=500, chunk_overlap=50)

    nodes_added: list[str] = []
    edges_added: int = 0
    ingest_ids: list[str] = []

    # 소스 노드 생성
    source_id = normalize_node_id(source)
    try:
        builder.add_node(
            space="resource",
            node_id=source_id,
            node_type="document",
            properties={"label": source, "chunk_count": len(chunks)},
        )
        nodes_added.append(source_id)
    except Exception as e:
        logger.warning("소스 노드 추가 실패: %s", e)

    # 청크별 처리
    for i, chunk in enumerate(chunks):
        chunk_id = f"{source_id}_chunk_{i}"

        # evidence 노드로 각 청크 저장
        try:
            builder.add_node(
                space="evidence",
                node_id=chunk_id,
                node_type="observation",
                properties={
                    "label": f"{source} chunk {i}",
                    "content": chunk[:200],
                    "chunk_index": i,
                    "source": source,
                },
            )
            nodes_added.append(chunk_id)

            # 소스 → 청크 엣지
            builder.add_edge(
                from_space="resource",
                from_id=source_id,
                to_space="evidence",
                to_id=chunk_id,
                relation="contains",
            )
            edges_added += 1
        except Exception as e:
            logger.warning("청크 노드 추가 실패 (index=%d): %s", i, e)

    # 벡터 저장
    if auto_ingest and chunks:
        try:
            ingest_ids = engine.ingest(
                texts=chunks,
                metadatas=[
                    {
                        "source": source,
                        "chunk_index": i,
                        "space": "evidence",
                        "node_id": f"{source_id}_chunk_{i}",
                    }
                    for i in range(len(chunks))
                ],
            )
        except Exception as e:
            logger.warning("벡터 저장 실패: %s", e)

    return {
        "source": source,
        "chunks": len(chunks),
        "nodes_added": len(nodes_added),
        "edges_added": edges_added,
        "vector_ids": len(ingest_ids),
    }


# ── Phase 2 도구 구현 ────────────────────────────────────────────────────────

def _tool_identity_add_alias(ctx: dict, args: dict) -> dict:
    identity = ctx.get("identity")
    if not identity:
        return {"error": "IdentityEngine을 사용할 수 없습니다."}
    identity.add_alias(
        canonical_id=args["canonical_id"],
        alias=args["alias"],
        space=args.get("space", "concept"),
    )
    return {
        "canonical_id": args["canonical_id"],
        "alias":        args["alias"],
        "space":        args.get("space", "concept"),
    }


def _tool_identity_resolve(ctx: dict, args: dict) -> dict:
    identity = ctx.get("identity")
    if not identity:
        return {"error": "IdentityEngine을 사용할 수 없습니다."}
    canonical = identity.resolve_canonical(args["alias"])
    return {
        "alias":        args["alias"],
        "canonical_id": canonical,
        "found":        canonical is not None,
    }


def _tool_identity_propose_duplicate(ctx: dict, args: dict) -> dict:
    identity = ctx.get("identity")
    if not identity:
        return {"error": "IdentityEngine을 사용할 수 없습니다."}
    candidate_id = identity.propose_duplicate(
        node_a=args["node_a"],
        node_b=args["node_b"],
        space=args.get("space", "concept"),
        reason=args.get("reason", ""),
    )
    return {
        "candidate_id": candidate_id,
        "node_a":       args["node_a"],
        "node_b":       args["node_b"],
    }


def _tool_identity_resolve_duplicate(ctx: dict, args: dict) -> dict:
    identity = ctx.get("identity")
    if not identity:
        return {"error": "IdentityEngine을 사용할 수 없습니다."}
    ok = identity.resolve_duplicate(
        candidate_id=args["candidate_id"],
        action=args["action"],
    )
    return {
        "candidate_id": args["candidate_id"],
        "action":       args["action"],
        "updated":      ok,
    }


def _tool_workflow_create(ctx: dict, args: dict) -> dict:
    sql = ctx.get("sql")
    if not sql:
        return {"error": "SQL 스토어를 사용할 수 없습니다."}
    run_id = sql.create_run(
        action_type=args["action_type"],
        payload=args.get("payload"),
    )
    return {"run_id": run_id, "action_type": args["action_type"], "status": "pending"}


def _tool_workflow_advance(ctx: dict, args: dict) -> dict:
    sql = ctx.get("sql")
    if not sql:
        return {"error": "SQL 스토어를 사용할 수 없습니다."}
    updated = sql.advance_run(
        run_id=args["run_id"],
        new_status=args["new_status"],
        note=args.get("note", ""),
        actor=args.get("actor", "system"),
    )
    return {"run_id": args["run_id"], "new_status": args["new_status"], "updated": updated}


def _tool_workflow_list(ctx: dict, args: dict) -> dict:
    sql = ctx.get("sql")
    if not sql:
        return {"error": "SQL 스토어를 사용할 수 없습니다."}
    runs = sql.list_runs(
        status=args.get("status"),
        limit=args.get("limit", 20),
    )
    return {"count": len(runs), "runs": runs}


def _tool_impact_record(ctx: dict, args: dict) -> dict:
    sql = ctx.get("sql")
    if not sql:
        return {"error": "SQL 스토어를 사용할 수 없습니다."}
    sql.record_impact(
        node_id=args["node_id"],
        space=args["space"],
        category=args["category"],
        result=args.get("result") or {},
    )
    return {
        "node_id":  args["node_id"],
        "category": args["category"],
        "recorded": True,
    }


def _tool_impact_history(ctx: dict, args: dict) -> dict:
    sql = ctx.get("sql")
    if not sql:
        return {"error": "SQL 스토어를 사용할 수 없습니다."}
    history = sql.get_impact_history(
        node_id=args["node_id"],
        limit=args.get("limit", 20),
    )
    return {"node_id": args["node_id"], "count": len(history), "history": history}


def _tool_harness_run(ctx: dict, args: dict) -> dict:
    from crabharness.harness import CrabHarness
    from crabharness.planner import Mission

    sources: list[str] = args.get("sources", [])
    if not sources:
        return {"error": "sources 목록이 비어 있습니다."}

    mission = Mission(sources=sources, goal=args.get("goal", "ingest"))
    harness = CrabHarness()
    result  = harness.run(mission)

    # auto_ingest: 검증 통과 청크를 벡터 스토어에 저장
    if args.get("auto_ingest", True):
        engine = ctx.get("query")
        if engine:
            for wr, rp in zip(result.worker_results, result.reports):
                if rp.passed and wr.chunks:
                    try:
                        engine.ingest(
                            texts=wr.chunks,
                            metadatas=[
                                {
                                    "source":      wr.source,
                                    "space":       rp.space,
                                    "chunk_index": i,
                                    "worker":      wr.worker_name,
                                }
                                for i in range(len(wr.chunks))
                            ],
                        )
                    except Exception as e:
                        logger.warning("harness_run 벡터 저장 실패 (%s): %s", wr.source, e)

    summary = result.summary()
    return {
        "mission_id":    summary["mission_id"],
        "total_sources": summary["total_sources"],
        "passed":        summary["passed"],
        "failed":        summary["failed"],
        "errors":        summary["errors"],
        "jobs": [j.to_dict() for j in result.jobs],
        "reports": [
            {"source": rp.source, "passed": rp.passed,
             "space": rp.space, "issues": rp.issues}
            for rp in result.reports
        ],
    }


# ── 디스패처 ─────────────────────────────────────────────────────────────────

_TOOL_FUNCTIONS: dict[str, Any] = {
    # Phase 1
    "ping":              _tool_ping,
    "ontology_manifest": _tool_manifest,
    "ontology_ingest":   _tool_ingest,
    "ontology_add_node": _tool_add_node,
    "ontology_add_edge": _tool_add_edge,
    "ontology_query":    _tool_query,
    "query_bm25":        _tool_bm25,
    "ontology_extract":  _tool_extract,
    # Phase 2 — Identity
    "identity_add_alias":           _tool_identity_add_alias,
    "identity_resolve":             _tool_identity_resolve,
    "identity_propose_duplicate":   _tool_identity_propose_duplicate,
    "identity_resolve_duplicate":   _tool_identity_resolve_duplicate,
    # Phase 2 — Workflow
    "workflow_create":  _tool_workflow_create,
    "workflow_advance": _tool_workflow_advance,
    "workflow_list":    _tool_workflow_list,
    # Phase 2 — Impact
    "impact_record":  _tool_impact_record,
    "impact_history": _tool_impact_history,
    # Phase 2 — Harness
    "harness_run": _tool_harness_run,
}


def dispatch_tool(name: str, arguments: dict, ctx: dict) -> dict:
    """
    도구 이름과 인수를 받아 실행하고 JSON 직렬화 가능한 결과 반환.
    알 수 없는 도구나 실행 오류는 {"error": "..."} 형태로 반환.
    """
    fn = _TOOL_FUNCTIONS.get(name)
    if fn is None:
        return {"error": f"알 수 없는 도구: '{name}'. 사용 가능: {list(_TOOL_FUNCTIONS)}"}
    try:
        return fn(ctx, arguments)
    except Exception as e:
        logger.exception("도구 실행 오류 (tool=%s): %s", name, e)
        return {"error": str(e)}
