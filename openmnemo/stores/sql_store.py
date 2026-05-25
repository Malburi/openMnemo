"""SQLite / PostgreSQL 관계형 스토어 어댑터."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class SQLStore:
    """
    SQLAlchemy raw SQL 기반 관계형 스토어.
    SQLite (기본) / PostgreSQL 전환 가능.

    테이블:
        ontology_nodes   — 노드 레지스트리
        ontology_edges   — 엣지 레지스트리
        impact_records   — 영향 분석 결과
        rebac_policies   — 접근 제어 정책
        workflow_runs    — 워크플로우 실행 상태
        action_log       — 실행 이력 (append-only)

    사용 예:
        store = SQLStore(url="sqlite:///./my_mcp.db")
        store.register_node(space="concept", node_type="entity", node_id="rag")
    """

    def __init__(self, url: str = "sqlite:///./my_mcp.db") -> None:
        self._url = url
        self._engine = None
        self._available = False
        self._is_sqlite = url.startswith("sqlite")
        self._connect()

    # ── 연결 관리 ──────────────────────────────────────────────────────────

    def _connect(self) -> None:
        try:
            from sqlalchemy import create_engine, text

            kwargs: dict[str, Any] = {}
            if self._is_sqlite:
                kwargs["connect_args"] = {"check_same_thread": False}

            self._engine = create_engine(self._url, **kwargs)
            self._text = text
            self._available = True
            self._create_tables()
            logger.info("SQL 연결 성공: %s", self._url)
        except Exception as e:
            self._available = False
            logger.warning("SQL 연결 실패 (비활성 모드): %s", e)

    def _create_tables(self) -> None:
        """필요한 테이블 생성 (없을 때만)."""
        if self._is_sqlite:
            pk_clause = "INTEGER PRIMARY KEY AUTOINCREMENT"
            json_type = "TEXT"
        else:
            pk_clause = "SERIAL PRIMARY KEY"
            json_type = "JSONB"

        ddl_statements = [
            f"""
            CREATE TABLE IF NOT EXISTS ontology_nodes (
                id          {pk_clause},
                space       TEXT NOT NULL,
                node_type   TEXT NOT NULL,
                node_id     TEXT NOT NULL,
                tenant_id   TEXT DEFAULT 'default',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                UNIQUE (space, node_id)
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS ontology_edges (
                id          {pk_clause},
                from_space  TEXT NOT NULL,
                from_id     TEXT NOT NULL,
                to_space    TEXT NOT NULL,
                to_id       TEXT NOT NULL,
                relation    TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                UNIQUE (from_space, from_id, to_space, to_id, relation)
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS impact_records (
                id          {pk_clause},
                node_id     TEXT NOT NULL,
                space       TEXT NOT NULL,
                category    TEXT NOT NULL,
                result      {json_type},
                created_at  TEXT NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS rebac_policies (
                id          {pk_clause},
                subject_id  TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                permission  TEXT NOT NULL,
                tenant_id   TEXT DEFAULT 'default',
                created_at  TEXT NOT NULL,
                UNIQUE (subject_id, resource_id, permission)
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS workflow_runs (
                run_id      TEXT PRIMARY KEY,
                action_type TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                payload     {json_type},
                receipt_id  TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS action_log (
                id          {pk_clause},
                run_id      TEXT NOT NULL,
                status      TEXT NOT NULL,
                note        TEXT,
                actor       TEXT DEFAULT 'system',
                timestamp   TEXT NOT NULL
            )
            """,
        ]

        with self._engine.begin() as conn:
            for stmt in ddl_statements:
                conn.execute(self._text(stmt))

    def _require(self) -> None:
        if not self._available:
            raise RuntimeError("SQL 스토어를 사용할 수 없습니다.")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── 노드 레지스트리 ────────────────────────────────────────────────────

    def register_node(
        self,
        space: str,
        node_type: str,
        node_id: str,
        tenant_id: str = "default",
    ) -> None:
        """노드 등록 또는 업데이트."""
        self._require()
        now = self._now()
        if self._is_sqlite:
            stmt = """
                INSERT INTO ontology_nodes (space, node_type, node_id, tenant_id, created_at, updated_at)
                VALUES (:space, :node_type, :node_id, :tenant_id, :now, :now)
                ON CONFLICT (space, node_id) DO UPDATE SET
                    node_type  = excluded.node_type,
                    updated_at = excluded.updated_at
            """
        else:
            stmt = """
                INSERT INTO ontology_nodes (space, node_type, node_id, tenant_id, created_at, updated_at)
                VALUES (:space, :node_type, :node_id, :tenant_id, :now, :now)
                ON CONFLICT (space, node_id) DO UPDATE SET
                    node_type  = EXCLUDED.node_type,
                    updated_at = EXCLUDED.updated_at
            """
        with self._engine.begin() as conn:
            conn.execute(
                self._text(stmt),
                {"space": space, "node_type": node_type, "node_id": node_id,
                 "tenant_id": tenant_id, "now": now},
            )

    def register_edge(
        self,
        from_space: str,
        from_id: str,
        to_space: str,
        to_id: str,
        relation: str,
    ) -> None:
        """엣지 등록 (중복 무시)."""
        self._require()
        if self._is_sqlite:
            stmt = """
                INSERT OR IGNORE INTO ontology_edges
                    (from_space, from_id, to_space, to_id, relation, created_at)
                VALUES (:fs, :fi, :ts, :ti, :rel, :now)
            """
        else:
            stmt = """
                INSERT INTO ontology_edges
                    (from_space, from_id, to_space, to_id, relation, created_at)
                VALUES (:fs, :fi, :ts, :ti, :rel, :now)
                ON CONFLICT DO NOTHING
            """
        with self._engine.begin() as conn:
            conn.execute(
                self._text(stmt),
                {"fs": from_space, "fi": from_id, "ts": to_space,
                 "ti": to_id, "rel": relation, "now": self._now()},
            )

    # ── 영향 기록 ──────────────────────────────────────────────────────────

    def record_impact(
        self,
        node_id: str,
        space: str,
        category: str,
        result: dict,
    ) -> None:
        """영향 분석 결과 기록."""
        self._require()
        with self._engine.begin() as conn:
            conn.execute(
                self._text("""
                    INSERT INTO impact_records (node_id, space, category, result, created_at)
                    VALUES (:node_id, :space, :category, :result, :now)
                """),
                {
                    "node_id": node_id,
                    "space": space,
                    "category": category,
                    "result": json.dumps(result, ensure_ascii=False),
                    "now": self._now(),
                },
            )

    def get_impact_history(self, node_id: str, limit: int = 20) -> list[dict]:
        """최근 영향 분석 이력 조회."""
        self._require()
        with self._engine.connect() as conn:
            rows = conn.execute(
                self._text("""
                    SELECT category, result, created_at
                    FROM impact_records
                    WHERE node_id = :node_id
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                {"node_id": node_id, "limit": limit},
            ).fetchall()
        return [
            {
                "category": r[0],
                "result": json.loads(r[1]) if r[1] else {},
                "created_at": r[2],
            }
            for r in rows
        ]

    # ── ReBAC 정책 ────────────────────────────────────────────────────────

    def upsert_policy(
        self,
        subject_id: str,
        resource_id: str,
        permission: str,
        tenant_id: str = "default",
    ) -> None:
        """접근 제어 정책 추가 또는 업데이트."""
        self._require()
        if self._is_sqlite:
            stmt = """
                INSERT OR REPLACE INTO rebac_policies
                    (subject_id, resource_id, permission, tenant_id, created_at)
                VALUES (:sub, :res, :perm, :tid, :now)
            """
        else:
            stmt = """
                INSERT INTO rebac_policies (subject_id, resource_id, permission, tenant_id, created_at)
                VALUES (:sub, :res, :perm, :tid, :now)
                ON CONFLICT (subject_id, resource_id, permission) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id
            """
        with self._engine.begin() as conn:
            conn.execute(
                self._text(stmt),
                {"sub": subject_id, "res": resource_id, "perm": permission,
                 "tid": tenant_id, "now": self._now()},
            )

    def check_policy(
        self,
        subject_id: str,
        resource_id: str,
        permission: str,
    ) -> bool:
        """접근 권한 확인."""
        self._require()
        with self._engine.connect() as conn:
            row = conn.execute(
                self._text("""
                    SELECT 1 FROM rebac_policies
                    WHERE subject_id = :sub AND resource_id = :res AND permission = :perm
                    LIMIT 1
                """),
                {"sub": subject_id, "res": resource_id, "perm": permission},
            ).fetchone()
        return row is not None

    def list_policies(self, subject_id: str | None = None) -> list[dict]:
        """정책 목록 조회."""
        self._require()
        with self._engine.connect() as conn:
            if subject_id:
                rows = conn.execute(
                    self._text(
                        "SELECT subject_id, resource_id, permission, tenant_id "
                        "FROM rebac_policies WHERE subject_id = :sub"
                    ),
                    {"sub": subject_id},
                ).fetchall()
            else:
                rows = conn.execute(
                    self._text(
                        "SELECT subject_id, resource_id, permission, tenant_id "
                        "FROM rebac_policies"
                    )
                ).fetchall()
        return [
            {"subject_id": r[0], "resource_id": r[1],
             "permission": r[2], "tenant_id": r[3]}
            for r in rows
        ]

    # ── 워크플로우 ────────────────────────────────────────────────────────

    def create_run(self, action_type: str, payload: dict | None = None) -> str:
        """워크플로우 실행 생성. run_id 반환."""
        self._require()
        run_id = str(uuid.uuid4())
        now = self._now()
        with self._engine.begin() as conn:
            conn.execute(
                self._text("""
                    INSERT INTO workflow_runs
                        (run_id, action_type, status, payload, created_at, updated_at)
                    VALUES (:run_id, :action_type, 'pending', :payload, :now, :now)
                """),
                {
                    "run_id": run_id,
                    "action_type": action_type,
                    "payload": json.dumps(payload or {}, ensure_ascii=False),
                    "now": now,
                },
            )
        self._append_log(run_id, "pending", "실행 생성")
        return run_id

    def advance_run(
        self,
        run_id: str,
        new_status: str,
        note: str = "",
        actor: str = "system",
    ) -> bool:
        """워크플로우 상태 전환. 성공 여부 반환."""
        self._require()
        now = self._now()
        with self._engine.begin() as conn:
            result = conn.execute(
                self._text("""
                    UPDATE workflow_runs
                    SET status = :status, updated_at = :now
                    WHERE run_id = :run_id
                """),
                {"status": new_status, "now": now, "run_id": run_id},
            )
            updated = result.rowcount > 0
        if updated:
            self._append_log(run_id, new_status, note, actor)
        return updated

    def get_run(self, run_id: str) -> dict | None:
        """워크플로우 실행 조회."""
        self._require()
        with self._engine.connect() as conn:
            row = conn.execute(
                self._text(
                    "SELECT run_id, action_type, status, payload, created_at, updated_at "
                    "FROM workflow_runs WHERE run_id = :run_id"
                ),
                {"run_id": run_id},
            ).fetchone()
        if not row:
            return None
        return {
            "run_id": row[0], "action_type": row[1], "status": row[2],
            "payload": json.loads(row[3]) if row[3] else {},
            "created_at": row[4], "updated_at": row[5],
        }

    def list_runs(self, status: str | None = None, limit: int = 20) -> list[dict]:
        """워크플로우 실행 목록 조회."""
        self._require()
        with self._engine.connect() as conn:
            if status:
                rows = conn.execute(
                    self._text(
                        "SELECT run_id, action_type, status, created_at "
                        "FROM workflow_runs WHERE status = :status "
                        "ORDER BY created_at DESC LIMIT :limit"
                    ),
                    {"status": status, "limit": limit},
                ).fetchall()
            else:
                rows = conn.execute(
                    self._text(
                        "SELECT run_id, action_type, status, created_at "
                        "FROM workflow_runs ORDER BY created_at DESC LIMIT :limit"
                    ),
                    {"limit": limit},
                ).fetchall()
        return [
            {"run_id": r[0], "action_type": r[1], "status": r[2], "created_at": r[3]}
            for r in rows
        ]

    def get_action_log(self, run_id: str) -> list[dict]:
        """워크플로우 실행 이력 조회."""
        self._require()
        with self._engine.connect() as conn:
            rows = conn.execute(
                self._text(
                    "SELECT status, note, actor, timestamp "
                    "FROM action_log WHERE run_id = :run_id ORDER BY timestamp ASC"
                ),
                {"run_id": run_id},
            ).fetchall()
        return [
            {"status": r[0], "note": r[1], "actor": r[2], "timestamp": r[3]}
            for r in rows
        ]

    def _append_log(
        self,
        run_id: str,
        status: str,
        note: str = "",
        actor: str = "system",
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                self._text("""
                    INSERT INTO action_log (run_id, status, note, actor, timestamp)
                    VALUES (:run_id, :status, :note, :actor, :ts)
                """),
                {"run_id": run_id, "status": status,
                 "note": note, "actor": actor, "ts": self._now()},
            )

    # ── 통계 ──────────────────────────────────────────────────────────────

    def table_counts(self) -> dict[str, int]:
        """테이블별 레코드 수 반환."""
        if not self._available:
            return {}
        tables = [
            "ontology_nodes", "ontology_edges", "impact_records",
            "rebac_policies", "workflow_runs", "action_log",
        ]
        counts: dict[str, int] = {}
        with self._engine.connect() as conn:
            for table in tables:
                row = conn.execute(
                    self._text(f"SELECT count(*) FROM {table}")
                ).fetchone()
                counts[table] = row[0] if row else 0
        return counts

    def ping(self) -> bool:
        """연결 상태 확인."""
        if not self._available:
            return False
        try:
            with self._engine.connect() as conn:
                conn.execute(self._text("SELECT 1"))
            return True
        except Exception:
            self._available = False
            return False
