"""Neo4j 그래프 DB 어댑터."""

from __future__ import annotations

import contextlib
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

_SPACE_LABELS = [
    "subject", "resource", "evidence", "concept",
    "claim", "community", "outcome", "lever", "policy",
]


class Neo4jStore:
    """
    Neo4j와의 모든 상호작용을 담당하는 어댑터.

    사용 예:
        store = Neo4jStore(uri="bolt://localhost:7687", user="neo4j", password="pw")
        store.upsert_node(space="concept", node_type="entity", node_id="rag", properties={"label": "RAG"})
        store.close()
    """

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._uri = uri
        self._user = user
        self._password = password
        self._driver = None
        self._lock = threading.Lock()
        self._available = False
        self._connect()

    # ── 연결 관리 ──────────────────────────────────────────────────────────

    def _connect(self) -> None:
        try:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(
                self._uri, auth=(self._user, self._password)
            )
            self._driver.verify_connectivity()
            self._available = True
            self.ensure_constraints()
            logger.info("Neo4j 연결 성공: %s", self._uri)
        except Exception as e:
            self._available = False
            logger.warning("Neo4j 연결 실패 (비활성 모드): %s", e)

    def close(self) -> None:
        if self._driver:
            self._driver.close()
            self._available = False

    @contextlib.contextmanager
    def _session(self):
        if not self._available or not self._driver:
            raise RuntimeError("Neo4j를 사용할 수 없습니다.")
        session = self._driver.session()
        try:
            yield session
        finally:
            session.close()

    # ── 스키마 관리 ────────────────────────────────────────────────────────

    def ensure_constraints(self) -> None:
        """공간별 노드 고유성 제약 조건 생성."""
        if not self._available:
            return
        try:
            with self._driver.session() as session:
                for label in _SPACE_LABELS:
                    session.run(
                        f"CREATE CONSTRAINT IF NOT EXISTS "
                        f"FOR (n:{label.capitalize()}) REQUIRE n.node_id IS UNIQUE"
                    )
        except Exception as e:
            logger.warning("제약 조건 생성 실패: %s", e)

    # ── 노드 CRUD ──────────────────────────────────────────────────────────

    def upsert_node(
        self,
        space: str,
        node_type: str,
        node_id: str,
        properties: dict[str, Any] | None = None,
    ) -> dict:
        """노드 생성 또는 업데이트. receipt_id와 타임스탬프를 자동 부여."""
        import uuid
        from datetime import datetime, timezone

        props = {k: v for k, v in (properties or {}).items() if v is not None}
        label = space.capitalize()
        now = datetime.now(timezone.utc).isoformat()
        receipt_id = str(uuid.uuid4())

        with self._session() as session:
            result = session.run(
                f"""
                MERGE (n:{label} {{node_id: $node_id}})
                ON CREATE SET
                    n += $props,
                    n.space      = $space,
                    n.node_type  = $node_type,
                    n.created_at = $now,
                    n.updated_at = $now,
                    n.receipt_id = $receipt_id
                ON MATCH SET
                    n += $props,
                    n.node_type  = $node_type,
                    n.updated_at = $now,
                    n.receipt_id = $receipt_id
                RETURN n
                """,
                node_id=node_id,
                space=space,
                node_type=node_type,
                props=props,
                now=now,
                receipt_id=receipt_id,
            )
            record = result.single()
            return dict(record["n"]) if record else {}

    def get_node(self, space: str, node_id: str) -> dict | None:
        """노드 조회. 없으면 None 반환."""
        label = space.capitalize()
        with self._session() as session:
            result = session.run(
                f"MATCH (n:{label} {{node_id: $node_id}}) RETURN n",
                node_id=node_id,
            )
            record = result.single()
            return dict(record["n"]) if record else None

    def delete_node(self, space: str, node_id: str) -> bool:
        """노드와 연결된 모든 관계를 삭제. 삭제 여부 반환."""
        label = space.capitalize()
        with self._session() as session:
            result = session.run(
                f"MATCH (n:{label} {{node_id: $node_id}}) "
                f"DETACH DELETE n RETURN count(n) AS cnt",
                node_id=node_id,
            )
            record = result.single()
            return bool(record and record["cnt"] > 0)

    # ── 엣지 CRUD ──────────────────────────────────────────────────────────

    def upsert_edge(
        self,
        from_space: str,
        from_id: str,
        to_space: str,
        to_id: str,
        relation: str,
        properties: dict[str, Any] | None = None,
    ) -> bool:
        """두 노드 간 관계 생성 또는 업데이트."""
        from datetime import datetime, timezone

        from_label = from_space.capitalize()
        to_label = to_space.capitalize()
        props = properties or {}
        now = datetime.now(timezone.utc).isoformat()

        with self._session() as session:
            result = session.run(
                f"""
                MATCH (a:{from_label} {{node_id: $from_id}})
                MATCH (b:{to_label}   {{node_id: $to_id}})
                MERGE (a)-[r:{relation.upper()}]->(b)
                ON CREATE SET r += $props, r.created_at = $now
                ON MATCH  SET r += $props, r.updated_at = $now
                RETURN count(r) AS cnt
                """,
                from_id=from_id,
                to_id=to_id,
                props=props,
                now=now,
            )
            record = result.single()
            return bool(record and record["cnt"] > 0)

    # ── 쿼리 ──────────────────────────────────────────────────────────────

    def run_cypher(self, query: str, params: dict | None = None) -> list[dict]:
        """임의의 Cypher 쿼리 실행."""
        with self._session() as session:
            result = session.run(query, **(params or {}))
            return [dict(r) for r in result]

    def find_neighbors(
        self,
        space: str,
        node_id: str,
        depth: int = 1,
        relation_filter: str | None = None,
    ) -> list[dict]:
        """인접 노드 탐색. depth 단계까지 연결된 노드 반환."""
        label = space.capitalize()
        rel_pattern = (
            f"[r:{relation_filter.upper()}*1..{depth}]"
            if relation_filter
            else f"[*1..{depth}]"
        )
        with self._session() as session:
            result = session.run(
                f"""
                MATCH (start:{label} {{node_id: $node_id}})-{rel_pattern}-(neighbor)
                RETURN DISTINCT neighbor, labels(neighbor) AS labels
                LIMIT 50
                """,
                node_id=node_id,
            )
            return [
                {"node": dict(r["neighbor"]), "labels": r["labels"]}
                for r in result
            ]

    def find_path(
        self,
        from_space: str,
        from_id: str,
        to_space: str,
        to_id: str,
        max_depth: int = 5,
    ) -> list[dict]:
        """두 노드 간 최단 경로 탐색."""
        from_label = from_space.capitalize()
        to_label = to_space.capitalize()

        with self._session() as session:
            result = session.run(
                f"""
                MATCH p = shortestPath(
                    (a:{from_label} {{node_id: $from_id}})-[*1..{max_depth}]-
                    (b:{to_label}   {{node_id: $to_id}})
                )
                RETURN [n IN nodes(p) | properties(n)] AS path_nodes,
                       [r IN relationships(p) | type(r)] AS relations
                """,
                from_id=from_id,
                to_id=to_id,
            )
            record = result.single()
            if not record:
                return []
            return [
                {"node": node, "relation": rel}
                for node, rel in zip(
                    record["path_nodes"],
                    record["relations"] + [None],
                )
            ]

    def count_nodes(self, space: str | None = None) -> int:
        """노드 수 반환. space 지정 시 해당 공간만 집계."""
        with self._session() as session:
            if space:
                label = space.capitalize()
                result = session.run(f"MATCH (n:{label}) RETURN count(n) AS cnt")
            else:
                result = session.run("MATCH (n) RETURN count(n) AS cnt")
            record = result.single()
            return record["cnt"] if record else 0

    def search_fulltext(
        self,
        query: str,
        top_k: int = 10,
        source_filter: str | None = None,
    ) -> list[dict]:
        """키워드 기반 노드 검색."""
        cypher = """
            MATCH (n)
            WHERE any(key IN keys(n) WHERE toLower(toString(n[key])) CONTAINS toLower($query))
        """
        params: dict[str, Any] = {"query": query}
        if source_filter:
            cypher += " AND n.source = $source"
            params["source"] = source_filter
        cypher += f" RETURN n LIMIT {top_k}"

        with self._session() as session:
            result = session.run(cypher, **params)
            return [dict(r["n"]) for r in result]

    def ping(self) -> bool:
        """연결 상태 확인."""
        if not self._available:
            return False
        try:
            with self._driver.session() as session:
                session.run("RETURN 1")
            return True
        except Exception:
            self._available = False
            return False
