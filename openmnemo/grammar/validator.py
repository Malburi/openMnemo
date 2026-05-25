"""MetaOntology 문법 검증 엔진."""

from __future__ import annotations

from dataclasses import dataclass

from .glossary import SPACES, RELATIONS, METADATA_LAYERS


@dataclass
class ValidationResult:
    valid: bool
    error: str | None = None

    def __bool__(self) -> bool:
        return self.valid


# 빌드 타임에 빠른 조회를 위한 역색인
_SPACE_NAMES: frozenset[str] = frozenset(SPACES.keys())
_NODE_TYPE_TO_SPACE: dict[str, str] = {
    node_type: space
    for space, meta in SPACES.items()
    for node_type in meta["node_types"]
}
_ALL_METADATA_KEYS: frozenset[str] = frozenset(
    key for keys in METADATA_LAYERS.values() for key in keys
)


def validate_node(space: str, node_type: str) -> ValidationResult:
    """노드의 공간과 타입이 문법에 맞는지 검증."""
    if space not in _SPACE_NAMES:
        return ValidationResult(
            False,
            f"알 수 없는 공간: '{space}'. 허용 목록: {sorted(_SPACE_NAMES)}",
        )

    allowed_types = SPACES[space]["node_types"]
    if node_type not in allowed_types:
        return ValidationResult(
            False,
            f"'{space}' 공간에서 허용되지 않는 노드 타입: '{node_type}'. "
            f"허용 목록: {allowed_types}",
        )

    return ValidationResult(True)


def validate_edge(
    from_space: str,
    to_space: str,
    relation: str,
) -> ValidationResult:
    """엣지의 방향과 관계 레이블이 문법에 맞는지 검증."""
    if from_space not in _SPACE_NAMES:
        return ValidationResult(False, f"알 수 없는 출발 공간: '{from_space}'")
    if to_space not in _SPACE_NAMES:
        return ValidationResult(False, f"알 수 없는 도착 공간: '{to_space}'")

    allowed = RELATIONS.get((from_space, to_space))
    if allowed is None:
        return ValidationResult(
            False,
            f"'{from_space}' → '{to_space}' 간 정의된 관계가 없습니다.",
        )

    if relation not in allowed:
        return ValidationResult(
            False,
            f"'{from_space}' → '{to_space}' 간 허용되지 않는 관계: '{relation}'. "
            f"허용 목록: {allowed}",
        )

    return ValidationResult(True)


def get_allowed_relations(from_space: str, to_space: str) -> list[str]:
    """두 공간 간 허용된 관계 목록 반환."""
    return RELATIONS.get((from_space, to_space), [])


def validate_metadata_layer(key: str) -> ValidationResult:
    """메타데이터 키가 정의된 계층에 속하는지 검증."""
    if key in _ALL_METADATA_KEYS:
        return ValidationResult(True)
    return ValidationResult(
        False,
        f"정의되지 않은 메타데이터 키: '{key}'. "
        f"허용 목록: {sorted(_ALL_METADATA_KEYS)}",
    )


def validate_rebac_permission(permission: str) -> ValidationResult:
    """ReBAC 권한 레이블이 policy 공간의 관계에 속하는지 검증."""
    policy_relations: set[str] = set()
    for (f, _), rels in RELATIONS.items():
        if f == "policy":
            policy_relations.update(rels)

    if permission in policy_relations:
        return ValidationResult(True)
    return ValidationResult(
        False,
        f"정의되지 않은 ReBAC 권한: '{permission}'. "
        f"허용 목록: {sorted(policy_relations)}",
    )


def validate_node_properties(
    space: str,
    node_type: str,
    properties: dict,
) -> ValidationResult:
    """노드 속성 딕셔너리의 기본 타입 검증 (str, int, float, bool만 허용)."""
    node_result = validate_node(space, node_type)
    if not node_result:
        return node_result

    allowed_types = (str, int, float, bool)
    invalid_keys = [
        f"{k}({type(v).__name__})"
        for k, v in properties.items()
        if not isinstance(v, allowed_types) and v is not None
    ]
    if invalid_keys:
        return ValidationResult(
            False,
            f"허용되지 않는 속성 타입 (str/int/float/bool/None 만 허용): {invalid_keys}",
        )

    return ValidationResult(True)


def describe_grammar() -> dict:
    """전체 문법을 JSON 직렬화 가능한 형태로 반환."""
    return {
        "spaces": {
            space: {
                "description": meta["description"],
                "node_types": meta["node_types"],
            }
            for space, meta in SPACES.items()
        },
        "relations": {
            f"{f}->{t}": rels
            for (f, t), rels in RELATIONS.items()
        },
        "metadata_layers": METADATA_LAYERS,
    }
