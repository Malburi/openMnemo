"""OntologyBuilder — 노드·엣지를 3개 스토어에 동시 기록."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from openmnemo.grammar.validator import validate_node, validate_edge
from openmnemo.stores.neo4j_store import Neo4jStore
from openmnemo.stores.mongo_store import MongoStore
from openmnemo.stores.sql_store import SQLStore

logger = logging.getLogger(__name__)

_SPACE_DEFAULT_TYPE: dict[str, str] = {
    "subject":   "person",
    "resource":  "document",
    "evidence":  "observation",
    "concept":   "entity",
    "claim":     "assertion",
    "community": "cluster",
    "outcome":   "kpi",
    "lever":     "parameter",
    "policy":    "rule",
}


def _receipt() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OntologyBuilder:
    """
    노드·엣지를 Neo4j(그래프), MongoDB(원문), SQL(레지스트리)에 동시 기록.

    개별 스토어 실패는 로깅 후 계속 진행 — 한 스토어 장애가 전체를 막지 않음.

    사용 예:
        builder = OntologyBuilder(neo4j=neo4j_store, mongo=mongo_store, sql=sql_store)
        receipt = builder.add_node(
            space="concept", node_type="entity", node_id="rag",
            properties={"label": "RAG", "description": "검색 증강 생성"}
        )
    """

    def __init__(
        self,
        neo4j: Neo4jStore | None = None,
        mongo: MongoStore | None = None,
        sql: SQLStore | None = None,
        tenant_id: str = "default",
    ) -> None:
        self._neo4j = neo4j
        self._mongo = mongo
        self._sql = sql
        self._tenant_id = tenant_id

    # ── 노드 ──────────────────────────────────────────────────────────────

    def add_node(
        self,
        space: str,
        node_id: str,
        properties: dict[str, Any] | None = None,
        node_type: str | None = None,
    ) -> str:
        """
        노드를 3개 스토어에 기록.

        node_type 미지정 시 space 기본 타입 사용.
        반환값: receipt_id (추적용 UUID)
        """
        resolved_type = node_type or _SPACE_DEFAULT_TYPE.get(space, "entity")

        result = validate_node(space, resolved_type)
        if not result:
            raise ValueError(f"문법 검증 실패: {result.error}")

        receipt_id = _receipt()
        props = properties or {}

        # Neo4j
        if self._neo4j:
            try:
                self._neo4j.upsert_node(
                    space=space,
                    node_type=resolved_type,
                    node_id=node_id,
                    properties={**props, "receipt_id": receipt_id},
                )
            except Exception as e:
                logger.warning("[Neo4j] add_node 실패 (node_id=%s): %s", node_id, e)

        # MongoDB
        if self._mongo:
            try:
                self._mongo.upsert_node_doc(
                    space=space,
                    node_id=node_id,
                    node_type=resolved_type,
                    properties={**props, "receipt_id": receipt_id},
                )
                self._mongo.log_event(
                    "add_node",
                    {"space": space, "node_id": node_id, "receipt_id": receipt_id},
                )
            except Exception as e:
                logger.warning("[Mongo] add_node 실패 (node_id=%s): %s", node_id, e)

        # SQL
        if self._sql:
            try:
                self._sql.register_node(
                    space=space,
                    node_type=resolved_type,
                    node_id=node_id,
                    tenant_id=self._tenant_id,
                )
            except Exception as e:
                logger.warning("[SQL] add_node 실패 (node_id=%s): %s", node_id, e)

        logger.debug(
            "add_node 완료: space=%s, node_id=%s, receipt=%s",
            space, node_id, receipt_id,
        )
        return receipt_id

    # ── 엣지 ──────────────────────────────────────────────────────────────

    def add_edge(
        self,
        from_space: str,
        from_id: str,
        to_space: str,
        to_id: str,
        relation: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """
        엣지를 Neo4j + SQL에 기록. MongoDB는 감사 로그만 기록.

        반환값: receipt_id
        """
        result = validate_edge(from_space, to_space, relation)
        if not result:
            raise ValueError(f"엣지 문법 검증 실패: {result.error}")

        receipt_id = _receipt()

        # Neo4j
        if self._neo4j:
            try:
                self._neo4j.upsert_edge(
                    from_space=from_space,
                    from_id=from_id,
                    to_space=to_space,
                    to_id=to_id,
                    relation=relation,
                    properties={**(properties or {}), "receipt_id": receipt_id},
                )
            except Exception as e:
                logger.warning(
                    "[Neo4j] add_edge 실패 (%s->%s %s): %s",
                    from_id, to_id, relation, e,
                )

        # SQL
        if self._sql:
            try:
                self._sql.register_edge(
                    from_space=from_space,
                    from_id=from_id,
                    to_space=to_space,
                    to_id=to_id,
                    relation=relation,
                )
            except Exception as e:
                logger.warning(
                    "[SQL] add_edge 실패 (%s->%s): %s", from_id, to_id, e,
                )

        # MongoDB 감사 로그
        if self._mongo:
            try:
                self._mongo.log_event(
                    "add_edge",
                    {
                        "from_space": from_space, "from_id": from_id,
                        "to_space": to_space, "to_id": to_id,
                        "relation": relation, "receipt_id": receipt_id,
                    },
                )
            except Exception as e:
                logger.debug("[Mongo] add_edge 감사 로그 실패: %s", e)

        logger.debug(
            "add_edge 완료: %s(%s) -[%s]-> %s(%s), receipt=%s",
            from_space, from_id, relation, to_space, to_id, receipt_id,
        )
        return receipt_id

    # ── 일괄 처리 ─────────────────────────────────────────────────────────

    def add_nodes_bulk(self, nodes: list[dict[str, Any]]) -> list[str]:
        """
        노드 목록 일괄 추가.

        nodes 형식:
            [{"space": ..., "node_id": ..., "node_type": ..., "properties": {...}}, ...]
        """
        receipts = []
        for node in nodes:
            try:
                receipt = self.add_node(
                    space=node["space"],
                    node_id=node["node_id"],
                    node_type=node.get("node_type"),
                    properties=node.get("properties"),
                )
                receipts.append(receipt)
            except Exception as e:
                logger.warning("add_nodes_bulk 항목 실패 (node_id=%s): %s", node.get("node_id"), e)
                receipts.append("")
        return receipts

    def add_edges_bulk(self, edges: list[dict[str, Any]]) -> list[str]:
        """
        엣지 목록 일괄 추가.

        edges 형식:
            [{"from_space": ..., "from_id": ..., "to_space": ..., "to_id": ..., "relation": ...}, ...]
        """
        receipts = []
        for edge in edges:
            try:
                receipt = self.add_edge(
                    from_space=edge["from_space"],
                    from_id=edge["from_id"],
                    to_space=edge["to_space"],
                    to_id=edge["to_id"],
                    relation=edge["relation"],
                    properties=edge.get("properties"),
                )
                receipts.append(receipt)
            except Exception as e:
                logger.warning(
                    "add_edges_bulk 항목 실패 (%s->%s): %s",
                    edge.get("from_id"), edge.get("to_id"), e,
                )
                receipts.append("")
        return receipts

    # ── 조회 ──────────────────────────────────────────────────────────────

    def get_node(self, space: str, node_id: str) -> dict | None:
        """Neo4j 우선 조회, 실패 시 MongoDB 폴백."""
        if self._neo4j:
            try:
                result = self._neo4j.get_node(space, node_id)
                if result:
                    return result
            except Exception as e:
                logger.warning("[Neo4j] get_node 실패: %s", e)

        if self._mongo:
            try:
                return self._mongo.get_node_doc(space, node_id)
            except Exception as e:
                logger.warning("[Mongo] get_node 폴백 실패: %s", e)

        return None

    def delete_node(self, space: str, node_id: str) -> bool:
        """3개 스토어에서 노드 삭제. 하나라도 성공하면 True."""
        deleted = False

        if self._neo4j:
            try:
                deleted |= self._neo4j.delete_node(space, node_id)
            except Exception as e:
                logger.warning("[Neo4j] delete_node 실패: %s", e)

        if self._mongo:
            try:
                deleted |= self._mongo.delete_node_doc(space, node_id)
            except Exception as e:
                logger.warning("[Mongo] delete_node 실패: %s", e)

        if self._mongo:
            try:
                self._mongo.log_event(
                    "delete_node", {"space": space, "node_id": node_id}
                )
            except Exception:
                pass

        return deleted

    # ── 통계 ──────────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """스토어별 통계 반환."""
        result: dict[str, Any] = {}
        if self._neo4j:
            result["neo4j"] = {
                s: self._neo4j.count_nodes(s)
                for s in ["subject", "resource", "evidence", "concept",
                           "claim", "community", "outcome", "lever", "policy"]
            }
        if self._mongo:
            result["mongo"] = self._mongo.collection_stats()
        if self._sql:
            result["sql"] = self._sql.table_counts()
        return result
