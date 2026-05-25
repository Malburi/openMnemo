"""MetaOntology 공식 용어 정의 — 9개 공간, 관계, 영향 카테고리."""

from __future__ import annotations

# ── 9개 온톨로지 공간 ────────────────────────────────────────────────────────
SPACES: dict[str, dict] = {
    "subject": {
        "description": "정체성과 행위성을 가진 주체 (사람, 시스템, 에이전트)",
        "node_types": ["person", "agent", "system", "organization", "role"],
        "examples": ["현민섭", "GPT-4", "백엔드팀"],
    },
    "resource": {
        "description": "문서, 데이터셋, API, 도구 등 참조 가능한 자원",
        "node_types": ["document", "dataset", "api", "tool", "file", "url"],
        "examples": ["논문 PDF", "REST API", "GitHub 저장소"],
    },
    "evidence": {
        "description": "관찰된 사실, 로그, 실험 결과 등 근거 데이터",
        "node_types": ["log", "observation", "metric", "experiment_result", "trace"],
        "examples": ["응답시간 200ms 측정값", "에러 로그"],
    },
    "concept": {
        "description": "추상적 개념, 엔티티, 도메인 지식",
        "node_types": ["entity", "abstraction", "pattern", "theory", "keyword"],
        "examples": ["임베딩", "트랜잭션", "RAG"],
    },
    "claim": {
        "description": "근거 기반 주장, 결론, 가설",
        "node_types": ["assertion", "hypothesis", "conclusion", "finding"],
        "examples": ["A가 B보다 성능이 좋다", "이 버그의 원인은 X다"],
    },
    "community": {
        "description": "그룹, 클러스터, 요약 집합",
        "node_types": ["cluster", "group", "summary", "topic", "category"],
        "examples": ["백엔드 팀", "AI 논문 그룹"],
    },
    "outcome": {
        "description": "KPI, 목표, 위험, 영향 결과",
        "node_types": ["kpi", "goal", "risk", "impact", "metric_result"],
        "examples": ["응답시간 200ms 목표", "보안 취약점 위험"],
    },
    "lever": {
        "description": "조정 가능한 제어 변수, 파라미터",
        "node_types": ["parameter", "config", "threshold", "flag", "weight"],
        "examples": ["chunk_size=500", "learning_rate=0.001"],
    },
    "policy": {
        "description": "규칙, 접근 제어, 거버넌스 정책",
        "node_types": ["rule", "permission", "constraint", "governance", "protocol"],
        "examples": ["관리자만 삭제 가능", "데이터 보존 30일"],
    },
}

# ── 공간 간 허용 관계 ────────────────────────────────────────────────────────
# 키: (from_space, to_space) → 허용 관계 목록
RELATIONS: dict[tuple[str, str], list[str]] = {
    # subject ↔ resource
    ("subject", "resource"): ["owns", "manages", "created", "can_view", "can_edit", "uses"],
    ("resource", "subject"): ["owned_by", "managed_by", "created_by"],

    # subject ↔ subject
    ("subject", "subject"): ["knows", "reports_to", "collaborates_with", "is_part_of"],

    # subject ↔ concept
    ("subject", "concept"): ["understands", "specializes_in", "coined"],
    ("concept", "subject"): ["defined_by", "maintained_by"],

    # subject ↔ community
    ("subject", "community"): ["belongs_to", "leads"],
    ("community", "subject"): ["includes", "governed_by"],

    # evidence ↔ claim
    ("evidence", "claim"): ["supports", "contradicts", "is_neutral_to", "timestamps"],
    ("claim", "evidence"): ["supported_by", "contradicted_by", "references"],

    # evidence ↔ resource
    ("evidence", "resource"): ["derived_from", "extracted_from"],
    ("resource", "evidence"): ["generates", "contains"],

    # concept ↔ concept
    ("concept", "concept"): ["is_a", "part_of", "related_to", "contradicts", "extends"],

    # concept ↔ resource
    ("concept", "resource"): ["described_in", "exemplified_by"],
    ("resource", "concept"): ["defines", "discusses", "introduces"],

    # claim ↔ outcome
    ("claim", "outcome"): ["predicts", "implies", "targets"],
    ("outcome", "claim"): ["validated_by", "challenged_by"],

    # lever ↔ outcome
    ("lever", "outcome"): ["raises", "lowers", "optimizes", "affects"],
    ("outcome", "lever"): ["controlled_by", "depends_on"],

    # policy ↔ subject
    ("policy", "subject"): ["applies_to", "grants", "restricts"],
    ("subject", "policy"): ["governed_by", "complies_with"],

    # policy ↔ resource
    ("policy", "resource"): ["protects", "regulates_access_to"],
    ("resource", "policy"): ["subject_to"],

    # community ↔ resource
    ("community", "resource"): ["maintains", "references"],
    ("resource", "community"): ["used_by"],

    # outcome ↔ community
    ("outcome", "community"): ["reported_to", "affects"],
    ("community", "outcome"): ["tracks", "owns"],
}

# ── 영향 카테고리 I1~I7 ──────────────────────────────────────────────────────
IMPACT_CATEGORIES: dict[str, str] = {
    "I1": "데이터 변화 — 노드·엣지 추가/수정/삭제",
    "I2": "스키마 변화 — 타입·관계 정의 변경",
    "I3": "접근 제어 변화 — 정책·권한 변경",
    "I4": "다운스트림 영향 — 연결된 시스템·서비스 영향",
    "I5": "품질 영향 — 데이터 일관성·정확도 영향",
    "I6": "성능 영향 — 쿼리·인덱스 성능 변화",
    "I7": "감사 영향 — 규정 준수·추적성 변화",
}

# ── 메타데이터 계층 ─────────────────────────────────────────────────────────
METADATA_LAYERS: dict[str, list[str]] = {
    "existence":   ["created_at", "updated_at", "version", "status"],
    "quality":     ["confidence", "completeness", "accuracy", "source_reliability"],
    "relational":  ["tenant_id", "namespace", "tags", "labels"],
    "behavioral":  ["access_count", "last_accessed", "ttl", "priority"],
}

# ── 유틸 함수 ────────────────────────────────────────────────────────────────

def lookup_term(term: str) -> dict | None:
    """공간, 관계, 영향 카테고리 통합 검색."""
    term = term.strip().lower()

    if term in SPACES:
        return {"type": "space", "data": SPACES[term]}

    for (f, t), rels in RELATIONS.items():
        if term in [r.lower() for r in rels]:
            return {"type": "relation", "from_space": f, "to_space": t, "relations": rels}

    for code, desc in IMPACT_CATEGORIES.items():
        if term in (code.lower(), desc.lower()):
            return {"type": "impact", "code": code, "description": desc}

    return None


def full_glossary() -> dict:
    """전체 용어집을 JSON 직렬화 가능한 딕셔너리로 반환."""
    return {
        "spaces": SPACES,
        "relations": {f"{f}->{t}": rels for (f, t), rels in RELATIONS.items()},
        "impact_categories": IMPACT_CATEGORIES,
        "metadata_layers": METADATA_LAYERS,
    }
