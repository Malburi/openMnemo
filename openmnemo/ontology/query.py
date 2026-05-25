"""HybridQuery — 벡터 + BM25 + 그래프 하이브리드 검색 엔진."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from openmnemo.stores.chroma_store import ChromaStore
from openmnemo.stores.neo4j_store import Neo4jStore
from openmnemo.stores.sql_store import SQLStore

logger = logging.getLogger(__name__)

# 관계 유형별 엣지 가중치
_EDGE_WEIGHTS: dict[str, float] = {
    "supports":       0.7,
    "contradicts":    0.5,
    "is_a":           0.9,
    "part_of":        0.8,
    "related_to":     0.6,
    "described_in":   0.7,
    "owns":           0.8,
    "created":        0.7,
    "extends":        0.85,
}
_DEFAULT_EDGE_WEIGHT = 0.6

# 관계 쿼리 트리거 키워드 (적응형 프로파일링)
_RELATION_KEYWORDS = frozenset([
    "관계", "연결", "원인", "영향", "차이", "비교",
    "relation", "connect", "cause", "impact", "difference", "compare",
])


@dataclass
class QueryResult:
    """검색 결과 단위."""
    node_id: str
    score: float
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = "unknown"          # "vector" | "keyword" | "graph" | "hybrid"
    vector_score: float | None = None
    keyword_score: float | None = None
    graph_score: float | None = None

    def to_dict(self) -> dict:
        return {
            "node_id":      self.node_id,
            "score":        round(self.score, 4),
            "text":         self.text,
            "metadata":     self.metadata,
            "source":       self.source,
            "vector_score": self.vector_score,
            "keyword_score":self.keyword_score,
            "graph_score":  self.graph_score,
        }


class HybridQuery:
    """
    벡터(ChromaDB) + BM25 키워드(Neo4j) + 그래프 확장(Neo4j)을 결합한 검색.

    파이프라인:
        1. 벡터 유사도 검색
        2. BM25 키워드 검색
        3. 앵커 노드 기반 그래프 확장 (옵션)
        4. RRF 점수 합산 및 재순위
        5. ReBAC 접근 제어 필터링 (옵션)

    사용 예:
        engine = HybridQuery(chroma=chroma_store, neo4j=neo4j_store, sql=sql_store)
        results = engine.query("RAG 검색 방법", top_k=5)
    """

    def __init__(
        self,
        chroma: ChromaStore | None = None,
        neo4j: Neo4jStore | None = None,
        sql: SQLStore | None = None,
        rrf_k: int = 60,
        graph_depth: int = 1,
        graph_decay: float = 0.5,
    ) -> None:
        self._chroma = chroma
        self._neo4j = neo4j
        self._sql = sql
        self._rrf_k = rrf_k
        self._graph_depth = graph_depth
        self._graph_decay = graph_decay
        self._bm25_cache: dict[str, Any] | None = None

    # ── 메인 쿼리 ─────────────────────────────────────────────────────────

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        source_filter: str | None = None,
        min_score: float = 0.0,
        use_graph: bool = True,
        subject_id: str | None = None,    # ReBAC 필터용
    ) -> list[QueryResult]:
        """
        하이브리드 검색 실행.

        query_text: 자연어 쿼리
        top_k:      반환할 최대 결과 수
        source_filter: 특정 source(파일명 등)만 검색
        min_score:  최소 점수 임계값
        use_graph:  그래프 확장 여부
        subject_id: ReBAC 필터 적용할 주체 ID
        """
        is_relational = self._is_relational_query(query_text)
        fetch_k = max(top_k * 3, 20)

        # 1. 벡터 검색
        vec_results = self._vector_search(query_text, fetch_k, source_filter)

        # 2. BM25 키워드 검색
        kw_results = self._bm25_search(query_text, fetch_k, source_filter)

        # 3. 그래프 확장 (관계형 쿼리 또는 use_graph=True)
        graph_results: list[QueryResult] = []
        if use_graph and (is_relational or vec_results):
            anchor_ids = [r.node_id for r in (vec_results + kw_results)[:5]]
            graph_results = self._graph_expand(anchor_ids, query_text)

        # 4. RRF 합산
        merged = self._rrf_merge(vec_results, kw_results, graph_results, top_k * 2)

        # 5. ReBAC 필터
        if subject_id and self._sql:
            merged = self._policy_filter(merged, subject_id)

        # 점수 임계값 적용 및 top_k 제한
        filtered = [r for r in merged if r.score >= min_score]
        return filtered[:top_k]

    # ── 벡터 검색 ─────────────────────────────────────────────────────────

    def _vector_search(
        self,
        query_text: str,
        top_k: int,
        source_filter: str | None,
    ) -> list[QueryResult]:
        if not self._chroma:
            return []
        try:
            where = {"source": source_filter} if source_filter else None
            hits = self._chroma.query(query_text, top_k=top_k, where=where)
            return [
                QueryResult(
                    node_id=h["id"],
                    score=h["similarity"],
                    text=h["document"],
                    metadata=h["metadata"],
                    source="vector",
                    vector_score=h["similarity"],
                )
                for h in hits
            ]
        except Exception as e:
            logger.warning("벡터 검색 실패: %s", e)
            return []

    # ── BM25 키워드 검색 ──────────────────────────────────────────────────

    def _bm25_search(
        self,
        query_text: str,
        top_k: int,
        source_filter: str | None,
    ) -> list[QueryResult]:
        if not self._neo4j:
            return []
        try:
            hits = self._neo4j.search_fulltext(
                query=query_text,
                top_k=top_k,
                source_filter=source_filter,
            )
            results = []
            for i, h in enumerate(hits):
                # BM25 근사 점수: 순위 기반 감쇠
                score = 1.0 / math.log2(i + 2)
                results.append(
                    QueryResult(
                        node_id=h.get("node_id", h.get("id", str(i))),
                        score=score,
                        text=str(h.get("label", h.get("description", ""))),
                        metadata=h,
                        source="keyword",
                        keyword_score=score,
                    )
                )
            return results
        except Exception as e:
            logger.warning("BM25 검색 실패: %s", e)
            return []

    # ── 그래프 확장 ───────────────────────────────────────────────────────

    def _graph_expand(
        self,
        anchor_node_ids: list[str],
        query_text: str,
    ) -> list[QueryResult]:
        """앵커 노드의 이웃을 탐색하여 추가 관련 노드 발굴."""
        if not self._neo4j or not anchor_node_ids:
            return []

        seen: set[str] = set(anchor_node_ids)
        results: list[QueryResult] = []

        for anchor_id in anchor_node_ids[:3]:
            try:
                # node_id로 공간 추정 (Neo4j 검색)
                neighbors = self._neo4j.run_cypher(
                    """
                    MATCH (n {node_id: $nid})-[r]-(neighbor)
                    RETURN neighbor, type(r) AS rel_type
                    LIMIT 10
                    """,
                    {"nid": anchor_id},
                )
                for row in neighbors:
                    neighbor = row.get("neighbor", {})
                    nid = neighbor.get("node_id", "")
                    if not nid or nid in seen:
                        continue
                    seen.add(nid)

                    rel_type = row.get("rel_type", "")
                    weight = _EDGE_WEIGHTS.get(rel_type.lower(), _DEFAULT_EDGE_WEIGHT)
                    score = weight * self._graph_decay

                    results.append(
                        QueryResult(
                            node_id=nid,
                            score=score,
                            text=str(neighbor.get("label", neighbor.get("description", nid))),
                            metadata=neighbor,
                            source="graph",
                            graph_score=score,
                        )
                    )
            except Exception as e:
                logger.debug("그래프 확장 실패 (anchor=%s): %s", anchor_id, e)

        return results

    # ── RRF 점수 합산 ─────────────────────────────────────────────────────

    def _rrf_merge(
        self,
        vec: list[QueryResult],
        kw: list[QueryResult],
        graph: list[QueryResult],
        top_k: int,
    ) -> list[QueryResult]:
        """Reciprocal Rank Fusion으로 3개 결과 목록 합산."""
        scores: dict[str, float] = {}
        best: dict[str, QueryResult] = {}

        def _add(results: list[QueryResult]) -> None:
            for rank, r in enumerate(results):
                rrf = 1.0 / (self._rrf_k + rank + 1)
                scores[r.node_id] = scores.get(r.node_id, 0.0) + rrf
                if r.node_id not in best or r.score > best[r.node_id].score:
                    best[r.node_id] = r

        _add(vec)
        _add(kw)
        _add(graph)

        if not scores:
            return []

        max_score = max(scores.values())
        merged: list[QueryResult] = []
        for node_id, rrf_score in sorted(scores.items(), key=lambda x: -x[1]):
            r = best[node_id]
            merged.append(
                QueryResult(
                    node_id=r.node_id,
                    score=rrf_score / max_score,
                    text=r.text,
                    metadata=r.metadata,
                    source="hybrid" if sum([
                        r.vector_score is not None,
                        r.keyword_score is not None,
                        r.graph_score is not None,
                    ]) > 1 else r.source,
                    vector_score=r.vector_score,
                    keyword_score=r.keyword_score,
                    graph_score=r.graph_score,
                )
            )
        return merged[:top_k]

    # ── ReBAC 필터 ────────────────────────────────────────────────────────

    def _policy_filter(
        self,
        results: list[QueryResult],
        subject_id: str,
    ) -> list[QueryResult]:
        """SQL 정책 테이블 기반 접근 불가 노드 제거."""
        filtered = []
        for r in results:
            resource_id = r.metadata.get("resource_id", r.node_id)
            try:
                allowed = self._sql.check_policy(subject_id, resource_id, "can_view")
                if allowed:
                    filtered.append(r)
            except Exception:
                filtered.append(r)  # 정책 조회 실패 시 허용
        return filtered

    # ── 수집(Ingest) ──────────────────────────────────────────────────────

    def ingest(
        self,
        texts: list[str],
        metadatas: list[dict] | None = None,
        ids: list[str] | None = None,
    ) -> list[str]:
        """텍스트 청크를 ChromaDB에 저장. BM25 캐시 무효화."""
        if not self._chroma:
            raise RuntimeError("ChromaDB가 설정되지 않았습니다.")
        result = self._chroma.upsert_texts(texts=texts, metadatas=metadatas, ids=ids)
        self._bm25_cache = None  # 캐시 무효화
        return result

    # ── 적응형 프로파일링 ─────────────────────────────────────────────────

    def _is_relational_query(self, text: str) -> bool:
        """관계·연결 키워드 포함 여부로 그래프 확장 필요성 판단."""
        lower = text.lower()
        return any(kw in lower for kw in _RELATION_KEYWORDS)

    # ── BM25 캐시 무효화 ──────────────────────────────────────────────────

    def invalidate_bm25_cache(self) -> None:
        self._bm25_cache = None
