"""MongoDB 문서 스토어 어댑터."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class MongoStore:
    """
    MongoDB 어댑터 — 노드 원문, 소스 메타데이터, 감사 로그 보관.

    사용 예:
        store = MongoStore(uri="mongodb://localhost:27017", db_name="my_mcp")
        store.upsert_node_doc(space="concept", node_id="rag", properties={"label": "RAG"})
    """

    def __init__(self, uri: str, db_name: str = "my_mcp") -> None:
        self._uri = uri
        self._db_name = db_name
        self._client = None
        self._db = None
        self._available = False
        self._connect()

    # ── 연결 관리 ──────────────────────────────────────────────────────────

    def _connect(self) -> None:
        try:
            import pymongo

            self._client = pymongo.MongoClient(
                self._uri,
                serverSelectionTimeoutMS=5000,
            )
            self._client.server_info()
            self._db = self._client[self._db_name]
            self._available = True
            self._ensure_indexes()
            logger.info("MongoDB 연결 성공: %s / %s", self._uri, self._db_name)
        except Exception as e:
            self._available = False
            logger.warning("MongoDB 연결 실패 (비활성 모드): %s", e)

    def _ensure_indexes(self) -> None:
        """컬렉션별 인덱스 생성."""
        try:
            self._db["nodes"].create_index(
                [("space", 1), ("node_id", 1)], unique=True
            )
            self._db["sources"].create_index("source_id", unique=True)
            self._db["audit_log"].create_index([("timestamp", -1)])
        except Exception as e:
            logger.warning("인덱스 생성 실패: %s", e)

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._available = False

    def _require(self) -> None:
        if not self._available:
            raise RuntimeError("MongoDB를 사용할 수 없습니다.")

    # ── 노드 문서 ──────────────────────────────────────────────────────────

    def upsert_node_doc(
        self,
        space: str,
        node_id: str,
        properties: dict[str, Any] | None = None,
        node_type: str = "",
    ) -> dict:
        """노드 문서 저장 또는 업데이트."""
        self._require()
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "space": space,
            "node_id": node_id,
            "node_type": node_type,
            "properties": properties or {},
            "updated_at": now,
        }
        result = self._db["nodes"].find_one_and_update(
            {"space": space, "node_id": node_id},
            {
                "$set": doc,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
            return_document=True,
        )
        if result:
            result.pop("_id", None)
        return result or doc

    def get_node_doc(self, space: str, node_id: str) -> dict | None:
        """노드 문서 조회."""
        self._require()
        doc = self._db["nodes"].find_one({"space": space, "node_id": node_id})
        if doc:
            doc.pop("_id", None)
        return doc

    def list_nodes(
        self,
        space: str | None = None,
        node_type: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """노드 목록 조회. space·node_type 필터 지원."""
        self._require()
        query: dict[str, Any] = {}
        if space:
            query["space"] = space
        if node_type:
            query["node_type"] = node_type

        cursor = self._db["nodes"].find(query).limit(limit)
        result = []
        for doc in cursor:
            doc.pop("_id", None)
            result.append(doc)
        return result

    def delete_node_doc(self, space: str, node_id: str) -> bool:
        """노드 문서 삭제. 삭제 여부 반환."""
        self._require()
        result = self._db["nodes"].delete_one({"space": space, "node_id": node_id})
        return result.deleted_count > 0

    # ── 소스 원문 ──────────────────────────────────────────────────────────

    def upsert_source(
        self,
        source_id: str,
        raw_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """수집된 소스 원문 저장 또는 업데이트."""
        self._require()
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "source_id": source_id,
            "raw_text": raw_text,
            "metadata": metadata or {},
            "updated_at": now,
        }
        self._db["sources"].find_one_and_update(
            {"source_id": source_id},
            {
                "$set": doc,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        return doc

    def get_source(self, source_id: str) -> dict | None:
        """소스 원문 조회."""
        self._require()
        doc = self._db["sources"].find_one({"source_id": source_id})
        if doc:
            doc.pop("_id", None)
        return doc

    def list_sources(self, limit: int = 50) -> list[dict]:
        """소스 목록 조회."""
        self._require()
        result = []
        for doc in self._db["sources"].find().sort("updated_at", -1).limit(limit):
            doc.pop("_id", None)
            result.append(doc)
        return result

    # ── 감사 로그 ──────────────────────────────────────────────────────────

    def log_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        actor: str = "system",
    ) -> None:
        """감사 이벤트 기록. 실패해도 무시."""
        if not self._available:
            return
        try:
            self._db["audit_log"].insert_one({
                "event_type": event_type,
                "actor": actor,
                "payload": payload,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            logger.debug("감사 로그 기록 실패 (무시): %s", e)

    def get_audit_log(
        self,
        event_type: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """감사 로그 조회. event_type 필터 지원."""
        self._require()
        query: dict[str, Any] = {}
        if event_type:
            query["event_type"] = event_type

        result = []
        for doc in self._db["audit_log"].find(query).sort("timestamp", -1).limit(limit):
            doc.pop("_id", None)
            result.append(doc)
        return result

    # ── 통계 ──────────────────────────────────────────────────────────────

    def collection_stats(self) -> dict[str, int]:
        """컬렉션별 문서 수 반환."""
        if not self._available:
            return {}
        return {
            "nodes": self._db["nodes"].count_documents({}),
            "sources": self._db["sources"].count_documents({}),
            "audit_log": self._db["audit_log"].count_documents({}),
        }

    def ping(self) -> bool:
        """연결 상태 확인."""
        if not self._available:
            return False
        try:
            self._client.server_info()
            return True
        except Exception:
            self._available = False
            return False
