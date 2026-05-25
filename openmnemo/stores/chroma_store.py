"""ChromaDB 벡터 스토어 어댑터."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _make_id(text: str) -> str:
    """텍스트의 SHA256 해시로 고유 ID 생성."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean_metadata(meta: dict) -> dict:
    """ChromaDB 허용 타입(str, int, float, bool)만 남김.
    chromadb는 빈 metadata dict를 거부하므로 최소 1개 키를 보장."""
    allowed = (str, int, float, bool)
    cleaned = {k: v for k, v in meta.items() if isinstance(v, allowed)}
    if not cleaned:
        cleaned["_auto"] = True
    return cleaned


class ChromaStore:
    """
    ChromaDB 벡터 저장소 어댑터.

    로컬 모드 (기본):
        store = ChromaStore(collection="ontology")

    HTTP 서버 모드:
        store = ChromaStore(collection="ontology", mode="http", host="localhost", port=8000)
    """

    def __init__(
        self,
        collection: str = "ontology",
        mode: str = "local",
        path: str = "./.chroma",
        host: str = "localhost",
        port: int = 8000,
    ) -> None:
        self._collection_name = collection
        self._client = None
        self._collection = None
        self._available = False
        self._connect(mode=mode, path=path, host=host, port=port)

    # ── 연결 관리 ──────────────────────────────────────────────────────────

    def _connect(
        self,
        mode: str,
        path: str,
        host: str,
        port: int,
    ) -> None:
        try:
            import chromadb

            if mode == "http":
                self._client = chromadb.HttpClient(host=host, port=port)
            else:
                self._client = chromadb.PersistentClient(path=path)

            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self._available = True
            logger.info(
                "ChromaDB 연결 성공: collection=%s, mode=%s",
                self._collection_name, mode,
            )
        except Exception as e:
            self._available = False
            logger.warning("ChromaDB 연결 실패 (비활성 모드): %s", e)

    # ── 쓰기 ──────────────────────────────────────────────────────────────

    def add_texts(
        self,
        texts: list[str],
        metadatas: list[dict] | None = None,
        ids: list[str] | None = None,
    ) -> list[str]:
        """텍스트 청크 추가. ID 미지정 시 SHA256 자동 생성."""
        if not self._available:
            raise RuntimeError("ChromaDB를 사용할 수 없습니다.")

        ids = ids or [_make_id(t) for t in texts]
        metas = [_clean_metadata(m) for m in (metadatas or [{}] * len(texts))]

        self._collection.add(documents=texts, metadatas=metas, ids=ids)
        return ids

    def upsert_texts(
        self,
        texts: list[str],
        metadatas: list[dict] | None = None,
        ids: list[str] | None = None,
    ) -> list[str]:
        """텍스트 추가 또는 업데이트."""
        if not self._available:
            raise RuntimeError("ChromaDB를 사용할 수 없습니다.")

        ids = ids or [_make_id(t) for t in texts]
        metas = [_clean_metadata(m) for m in (metadatas or [{}] * len(texts))]

        self._collection.upsert(documents=texts, metadatas=metas, ids=ids)
        return ids

    def delete(self, ids: list[str]) -> None:
        """ID 목록으로 문서 삭제."""
        if not self._available:
            raise RuntimeError("ChromaDB를 사용할 수 없습니다.")
        self._collection.delete(ids=ids)

    def reset_collection(self) -> None:
        """컬렉션 전체 초기화."""
        if not self._available:
            raise RuntimeError("ChromaDB를 사용할 수 없습니다.")
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # ── 읽기 ──────────────────────────────────────────────────────────────

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        where: dict | None = None,
    ) -> list[dict[str, Any]]:
        """
        자연어 쿼리로 의미 기반 검색.

        반환 형식:
            [{"id": ..., "document": ..., "metadata": ..., "distance": ...}, ...]
        """
        if not self._available:
            raise RuntimeError("ChromaDB를 사용할 수 없습니다.")

        kwargs: dict[str, Any] = {
            "query_texts": [query_text],
            "n_results": min(top_k, self.count()),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        if kwargs["n_results"] == 0:
            return []

        results = self._collection.query(**kwargs)
        output = []
        for doc, meta, dist, doc_id in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
            results["ids"][0],
        ):
            output.append({
                "id": doc_id,
                "document": doc,
                "metadata": meta,
                "distance": dist,
                "similarity": max(0.0, 1.0 - dist),
            })
        return output

    def get_by_id(self, doc_id: str) -> dict | None:
        """ID로 단건 조회."""
        if not self._available:
            raise RuntimeError("ChromaDB를 사용할 수 없습니다.")

        result = self._collection.get(
            ids=[doc_id],
            include=["documents", "metadatas"],
        )
        if not result["ids"]:
            return None
        return {
            "id": result["ids"][0],
            "document": result["documents"][0],
            "metadata": result["metadatas"][0],
        }

    def count(self) -> int:
        """저장된 문서 수 반환."""
        if not self._available:
            return 0
        return self._collection.count()

    def ping(self) -> bool:
        """연결 상태 확인."""
        if not self._available:
            return False
        try:
            self._collection.count()
            return True
        except Exception:
            self._available = False
            return False
