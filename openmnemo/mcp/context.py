"""MCP 컨텍스트 — 스토어·엔진 지연 초기화."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_ctx: dict[str, Any] | None = None


def _get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def get_context() -> dict[str, Any]:
    """
    첫 호출 시에만 모든 스토어·엔진을 초기화해 반환.
    이후 호출은 캐시된 컨텍스트를 재사용.

    반환 딕셔너리 키:
        neo4j   — Neo4jStore   (연결 실패 시 None)
        chroma  — ChromaStore
        mongo   — MongoStore   (연결 실패 시 None)
        sql     — SQLStore
        builder — OntologyBuilder
        query   — HybridQuery
        identity— IdentityEngine
    """
    global _ctx
    if _ctx is not None:
        return _ctx

    logger.info("MCP 컨텍스트 초기화 시작...")

    # ── SQL (항상 초기화 — SQLite 폴백) ──────────────────────────────────
    from openmnemo.stores.sql_store import SQLStore
    sql_url = _get_env("SQL_URL", "sqlite:///./my_mcp.db")
    sql = SQLStore(url=sql_url)

    # ── Neo4j ─────────────────────────────────────────────────────────────
    from openmnemo.stores.neo4j_store import Neo4jStore
    neo4j: Neo4jStore | None = None
    neo4j_uri = _get_env("NEO4J_URI")
    if neo4j_uri:
        neo4j = Neo4jStore(
            uri=neo4j_uri,
            user=_get_env("NEO4J_USER", "neo4j"),
            password=_get_env("NEO4J_PASSWORD", ""),
        )
        if not neo4j.ping():
            logger.warning("Neo4j 연결 실패 — 그래프 기능 비활성화")
            neo4j = None

    # ── ChromaDB ──────────────────────────────────────────────────────────
    from openmnemo.stores.chroma_store import ChromaStore
    chroma_mode = _get_env("CHROMA_MODE", "local")
    chroma = ChromaStore(
        collection=_get_env("CHROMA_COLLECTION", "ontology"),
        mode=chroma_mode,
        path=_get_env("CHROMA_PATH", "./.chroma"),
        host=_get_env("CHROMA_HOST", "localhost"),
        port=int(_get_env("CHROMA_PORT", "8000")),
    )

    # ── MongoDB ───────────────────────────────────────────────────────────
    from openmnemo.stores.mongo_store import MongoStore
    mongo: MongoStore | None = None
    mongo_uri = _get_env("MONGO_URI")
    if mongo_uri:
        mongo = MongoStore(
            uri=mongo_uri,
            db_name=_get_env("MONGO_DB", "my_mcp"),
        )
        if not mongo.ping():
            logger.warning("MongoDB 연결 실패 — 감사 로그 비활성화")
            mongo = None

    # ── OntologyBuilder ───────────────────────────────────────────────────
    from openmnemo.ontology.builder import OntologyBuilder
    builder = OntologyBuilder(
        neo4j=neo4j,
        mongo=mongo,
        sql=sql,
        tenant_id=_get_env("TENANT_ID", "default"),
    )

    # ── HybridQuery ───────────────────────────────────────────────────────
    from openmnemo.ontology.query import HybridQuery
    query_engine = HybridQuery(
        chroma=chroma,
        neo4j=neo4j,
        sql=sql,
        rrf_k=int(_get_env("RRF_K", "60")),
        graph_depth=int(_get_env("GRAPH_DEPTH", "1")),
    )

    # ── IdentityEngine ────────────────────────────────────────────────────
    from openmnemo.ontology.identity import IdentityEngine
    identity = IdentityEngine(sql=sql)

    _ctx = {
        "neo4j":    neo4j,
        "chroma":   chroma,
        "mongo":    mongo,
        "sql":      sql,
        "builder":  builder,
        "query":    query_engine,
        "identity": identity,
    }

    active = [k for k, v in _ctx.items() if v is not None]
    logger.info("MCP 컨텍스트 초기화 완료. 활성 컴포넌트: %s", active)
    return _ctx


def reset_context() -> None:
    """테스트 또는 재시작 시 컨텍스트 초기화."""
    global _ctx
    _ctx = None
