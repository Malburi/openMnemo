"""IdentityEngine — 별칭 관리 및 중복 감지 (자동 병합 없음)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from openmnemo.stores.sql_store import SQLStore

logger = logging.getLogger(__name__)


class IdentityEngine:
    """
    엔티티 별칭(alias) 등록과 중복 후보 관리.

    설계 원칙: "No auto-merge" — 중복 후보는 제안만 하고, 인간이 승인/거절.

    DB 구조 (SQLStore에 테이블 추가):
        node_aliases        — 정규 ID ↔ 별칭 매핑
        duplicate_candidates — 병합 대기 후보 목록

    사용 예:
        engine = IdentityEngine(sql=sql_store)
        engine.add_alias(canonical_id="rag", alias="retrieval_augmented_generation")
        canonical = engine.resolve_canonical("retrieval_augmented_generation")
    """

    def __init__(self, sql: SQLStore) -> None:
        self._sql = sql
        self._ensure_tables()

    # ── 테이블 초기화 ─────────────────────────────────────────────────────

    def _ensure_tables(self) -> None:
        if not self._sql._available:
            return
        is_sqlite = self._sql._is_sqlite
        pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if is_sqlite else "SERIAL PRIMARY KEY"

        ddl = [
            f"""
            CREATE TABLE IF NOT EXISTS node_aliases (
                id           {pk},
                canonical_id TEXT NOT NULL,
                alias        TEXT NOT NULL,
                space        TEXT NOT NULL DEFAULT 'concept',
                created_at   TEXT NOT NULL,
                UNIQUE (alias)
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS duplicate_candidates (
                id           {pk},
                candidate_id TEXT NOT NULL DEFAULT (lower(hex(randomblob(16)))),
                node_a       TEXT NOT NULL,
                node_b       TEXT NOT NULL,
                space        TEXT NOT NULL DEFAULT 'concept',
                reason       TEXT,
                status       TEXT NOT NULL DEFAULT 'pending',
                proposed_at  TEXT NOT NULL,
                resolved_at  TEXT
            )
            """,
        ]
        with self._sql._engine.begin() as conn:
            for stmt in ddl:
                conn.execute(self._sql._text(stmt))

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _require(self) -> None:
        if not self._sql._available:
            raise RuntimeError("SQL 스토어를 사용할 수 없습니다.")

    # ── 별칭 관리 ─────────────────────────────────────────────────────────

    def add_alias(
        self,
        canonical_id: str,
        alias: str,
        space: str = "concept",
    ) -> None:
        """정규 ID에 별칭 등록. 이미 존재하면 무시."""
        self._require()
        if self._sql._is_sqlite:
            stmt = """
                INSERT OR IGNORE INTO node_aliases (canonical_id, alias, space, created_at)
                VALUES (:cid, :alias, :space, :now)
            """
        else:
            stmt = """
                INSERT INTO node_aliases (canonical_id, alias, space, created_at)
                VALUES (:cid, :alias, :space, :now)
                ON CONFLICT (alias) DO NOTHING
            """
        with self._sql._engine.begin() as conn:
            conn.execute(
                self._sql._text(stmt),
                {"cid": canonical_id, "alias": alias, "space": space, "now": self._now()},
            )
        logger.debug("별칭 등록: %s → canonical=%s", alias, canonical_id)

    def resolve_canonical(self, alias: str) -> str | None:
        """별칭으로 정규 ID 조회. 없으면 None."""
        self._require()
        with self._sql._engine.connect() as conn:
            row = conn.execute(
                self._sql._text(
                    "SELECT canonical_id FROM node_aliases WHERE alias = :alias LIMIT 1"
                ),
                {"alias": alias},
            ).fetchone()
        return row[0] if row else None

    def list_aliases(self, canonical_id: str) -> list[str]:
        """정규 ID에 등록된 모든 별칭 반환."""
        self._require()
        with self._sql._engine.connect() as conn:
            rows = conn.execute(
                self._sql._text(
                    "SELECT alias FROM node_aliases WHERE canonical_id = :cid ORDER BY created_at"
                ),
                {"cid": canonical_id},
            ).fetchall()
        return [r[0] for r in rows]

    def remove_alias(self, alias: str) -> bool:
        """별칭 삭제. 삭제 여부 반환."""
        self._require()
        with self._sql._engine.begin() as conn:
            result = conn.execute(
                self._sql._text("DELETE FROM node_aliases WHERE alias = :alias"),
                {"alias": alias},
            )
        return result.rowcount > 0

    # ── 중복 후보 관리 ────────────────────────────────────────────────────

    def propose_duplicate(
        self,
        node_a: str,
        node_b: str,
        space: str = "concept",
        reason: str = "",
    ) -> str:
        """중복 의심 노드 쌍 제안. candidate_id 반환."""
        self._require()
        candidate_id = str(uuid.uuid4()).replace("-", "")
        with self._sql._engine.begin() as conn:
            conn.execute(
                self._sql._text("""
                    INSERT INTO duplicate_candidates
                        (candidate_id, node_a, node_b, space, reason, status, proposed_at)
                    VALUES (:cid, :a, :b, :space, :reason, 'pending', :now)
                """),
                {
                    "cid": candidate_id,
                    "a": node_a, "b": node_b,
                    "space": space, "reason": reason,
                    "now": self._now(),
                },
            )
        logger.info("중복 후보 제안: %s ↔ %s (id=%s)", node_a, node_b, candidate_id)
        return candidate_id

    def resolve_duplicate(
        self,
        candidate_id: str,
        action: str,          # "approve" | "reject"
    ) -> bool:
        """중복 후보 승인 또는 거절."""
        if action not in ("approve", "reject"):
            raise ValueError("action은 'approve' 또는 'reject' 여야 합니다.")

        self._require()
        status = "approved" if action == "approve" else "rejected"
        with self._sql._engine.begin() as conn:
            result = conn.execute(
                self._sql._text("""
                    UPDATE duplicate_candidates
                    SET status = :status, resolved_at = :now
                    WHERE candidate_id = :cid AND status = 'pending'
                """),
                {"status": status, "now": self._now(), "cid": candidate_id},
            )
        return result.rowcount > 0

    def list_pending_duplicates(self, space: str | None = None) -> list[dict]:
        """승인 대기 중인 중복 후보 목록 조회."""
        self._require()
        with self._sql._engine.connect() as conn:
            if space:
                rows = conn.execute(
                    self._sql._text("""
                        SELECT candidate_id, node_a, node_b, space, reason, proposed_at
                        FROM duplicate_candidates
                        WHERE status = 'pending' AND space = :space
                        ORDER BY proposed_at DESC
                    """),
                    {"space": space},
                ).fetchall()
            else:
                rows = conn.execute(
                    self._sql._text("""
                        SELECT candidate_id, node_a, node_b, space, reason, proposed_at
                        FROM duplicate_candidates
                        WHERE status = 'pending'
                        ORDER BY proposed_at DESC
                    """)
                ).fetchall()
        return [
            {
                "candidate_id": r[0], "node_a": r[1], "node_b": r[2],
                "space": r[3], "reason": r[4], "proposed_at": r[5],
            }
            for r in rows
        ]

    def find_duplicates_by_name(
        self,
        name: str,
        space: str = "concept",
    ) -> list[dict[str, Any]]:
        """
        유사한 이름의 노드를 별칭 테이블에서 검색.
        (간단한 LIKE 검색 — 필요 시 벡터 유사도로 교체 가능)
        """
        self._require()
        with self._sql._engine.connect() as conn:
            rows = conn.execute(
                self._sql._text("""
                    SELECT canonical_id, alias, space
                    FROM node_aliases
                    WHERE space = :space AND (
                        alias        LIKE :pattern OR
                        canonical_id LIKE :pattern
                    )
                    LIMIT 20
                """),
                {"space": space, "pattern": f"%{name}%"},
            ).fetchall()
        return [
            {"canonical_id": r[0], "alias": r[1], "space": r[2]}
            for r in rows
        ]
