"""정규화 유틸 — 텍스트 클렌징, 노드 ID 표준화, 병합 도우미."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


# ── 텍스트 클렌징 ────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """
    Windows/DB 인코딩 오류 문자 제거 및 공백 정규화.
    ChromaDB metadata, Neo4j property에 저장 전 사용 권장.
    """
    # 유니코드 정규화 (NFC)
    text = unicodedata.normalize("NFC", text)
    # 제어 문자 제거 (탭·줄바꿈 제외)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # 연속 공백 단일화
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def clean_properties(props: dict[str, Any]) -> dict[str, Any]:
    """
    딕셔너리 속성값에서 허용되지 않는 타입 제거.
    str, int, float, bool, None만 유지.
    """
    allowed = (str, int, float, bool)
    cleaned: dict[str, Any] = {}
    for k, v in props.items():
        if v is None:
            cleaned[k] = v
        elif isinstance(v, allowed):
            cleaned[k] = clean_text(v) if isinstance(v, str) else v
        # list/dict는 JSON 직렬화 후 str로 변환
        elif isinstance(v, (list, dict)):
            import json
            cleaned[k] = json.dumps(v, ensure_ascii=False)
    return cleaned


# ── 노드 ID 표준화 ───────────────────────────────────────────────────────────

def normalize_node_id(raw_id: str) -> str:
    """
    노드 ID를 소문자 snake_case로 표준화.

    예:
        "GPT-4o"          → "gpt_4o"
        "Retrieval-Augmented Generation" → "retrieval_augmented_generation"
        "My API (v2)"     → "my_api_v2"
    """
    text = unicodedata.normalize("NFC", raw_id)
    text = text.lower()
    # 공백·하이픈·슬래시 → 언더스코어
    text = re.sub(r"[\s\-/]+", "_", text)
    # 허용되지 않는 문자 제거 (알파벳, 숫자, 언더스코어, 한글만 허용)
    text = re.sub(r"[^\w가-힣]", "", text)
    # 연속 언더스코어 단일화
    text = re.sub(r"_{2,}", "_", text)
    return text.strip("_")


def normalize_relation(relation: str) -> str:
    """관계 레이블을 UPPER_SNAKE_CASE로 표준화."""
    text = relation.strip().upper()
    text = re.sub(r"[\s\-]+", "_", text)
    return text


# ── 병합 도우미 ──────────────────────────────────────────────────────────────

def merge_properties(
    base: dict[str, Any],
    override: dict[str, Any],
    keep_base_on_conflict: bool = False,
) -> dict[str, Any]:
    """
    두 속성 딕셔너리 병합.

    keep_base_on_conflict=True: base 값 우선 (충돌 시 override 무시)
    keep_base_on_conflict=False: override 값 우선 (기본값)
    """
    merged = dict(base)
    for k, v in override.items():
        if k not in merged or not keep_base_on_conflict:
            merged[k] = v
    return clean_properties(merged)


def deduplicate_nodes(
    nodes: list[dict[str, Any]],
    key: str = "node_id",
) -> list[dict[str, Any]]:
    """
    node_id 기준 중복 제거. 나중에 나온 노드가 앞 노드를 덮어씀.
    """
    seen: dict[str, dict] = {}
    for node in nodes:
        k = node.get(key, "")
        if k:
            seen[k] = node
    return list(seen.values())


def split_text_to_chunks(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[str]:
    """
    텍스트를 겹침 청킹.
    LangChain 미설치 환경에서도 동작하는 순수 Python 구현.
    """
    text = clean_text(text)
    if len(text) <= chunk_size:
        return [text] if text else []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - chunk_overlap

    return chunks


# ── 요약 유틸 ────────────────────────────────────────────────────────────────

def truncate(text: str, max_len: int = 200, suffix: str = "...") -> str:
    """텍스트를 max_len 글자로 자르고 suffix 추가."""
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)] + suffix
