# CLAUDE.md — openMnemo

## 프로젝트 개요

**openMnemo**는 MetaOntology 기반 MCP(Model Context Protocol) 서버다.
Claude Code가 18개 MCP 도구를 통해 Neo4j, ChromaDB, SQLite, MongoDB 4개 스토어에
지식 그래프를 구축·검색·추론하는 범용 온톨로지 시스템이다.

- **패키지 진입점:** `openmnemo/mcp/server.py` (stdio JSON-RPC 2.0)
- **빌드 백엔드:** hatchling (`packages = ["openmnemo", "crabharness"]`)
- **Python:** 3.11+, 패키지 관리: `uv`

---

## 공통 명령어

```bash
uv sync                                     # 의존성 설치/동기화
uv run python -m openmnemo.mcp.server       # MCP 서버 직접 실행 (테스트용)
uv run python -X utf8 scripts/test_stores.py  # 4개 스토어 연결 테스트
uv run python -X utf8 scripts/test_mcp.py  # MCP 도구 단위 테스트
uv run python -X utf8 scripts/test_all.py  # 전체 테스트
uv run pytest                               # pytest 단위 테스트
uv run ruff check .                         # 린트
uv run mypy openmnemo                       # 타입 검사
```

> Windows에서 한글 출력이 깨지면 `-X utf8` 플래그를 추가한다.

---

## 아키텍처

### 4개 스토어 역할 분리

| 스토어 | 파일 | 저장 내용 | 필수 여부 |
|--------|------|-----------|-----------|
| **SQLite** | `openmnemo/stores/sql_store.py` | 노드·엣지 레지스트리, 워크플로우, 정책 | 항상 필수 |
| **ChromaDB** | `openmnemo/stores/chroma_store.py` | 텍스트 청크 임베딩 (벡터 검색) | 항상 필수 |
| **Neo4j** | `openmnemo/stores/neo4j_store.py` | 그래프 관계 (Cypher 쿼리 가능) | 선택 (없으면 그래프 기능 비활성) |
| **MongoDB** | `openmnemo/stores/mongo_store.py` | 감사 로그·원문 보관 | 선택 (없으면 로그 비활성) |

**중요:** PDF 청크 내용은 ChromaDB에 저장된다. Neo4j에는 구조화된 노드/엣지만 있고
`chunk_index`, `content`, `source` 같은 속성은 없다.
Neo4j 노드 실제 속성: `node_id`, `space`, `node_type`, `label`, `description`,
`receipt_id`, `created_at`, `updated_at`

### CrabHarness 파이프라인

PDF·URL 인제스트 전용 파이프라인 (`crabharness/`):

```
Mission(sources=[...])
  → Planner  — 소스 타입별 DelegationJob 생성
  → Workers  — pdf_parser / web_crawler 실행
  → Validator — 청크 품질 검증 (점수 기반)
  → Promoter  — ChromaDB 저장 + Neo4j 노드 등록
```

`harness_run` MCP 도구로만 진입하며, 직접 `CrabHarness` 클래스를 건드릴 필요는 없다.

### MCP 컨텍스트 초기화

`openmnemo/mcp/context.py`의 `get_context()`가 첫 도구 호출 시 4개 스토어를
한꺼번에 lazy 초기화하고 전역 캐시(`_ctx`)에 보관한다.
환경변수는 `.mcp.json`의 `env` 블록에서 주입 — `.env` 파일을 직접 읽지 않는다.

---

## 환경 설정

### .mcp.json (Claude Code 실행 환경 — gitignore됨)

```json
{
  "mcpServers": {
    "my-mcp": {
      "command": "C:\\Users\\HHI\\openMnemo\\.venv\\Scripts\\python.exe",
      "args": ["-m", "openmnemo.mcp.server"],
      "cwd": "C:/Users/HHI/openMnemo",
      "env": {
        "SQL_URL":        "sqlite:///./my_mcp.db",
        "CHROMA_PATH":    "./.chroma",
        "CHROMA_MODE":    "local",
        "NEO4J_URI":      "bolt://localhost:7687",
        "NEO4J_USER":     "neo4j",
        "NEO4J_PASSWORD": "openMnemo123",
        "MONGO_URI":      "",
        "TENANT_ID":      "default"
      }
    }
  }
}
```

Neo4j 포트: **7687** (Bolt). 7474는 Browser 전용이라 연결 안 됨.
Neo4j 비밀번호: `openMnemo123` (대소문자 구분, 중간 M이 대문자).

### .env (스크립트 직접 실행 시)

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=openMnemo123
SQL_URL=sqlite:///./my_mcp.db
CHROMA_MODE=local
CHROMA_PATH=./.chroma
OPENAI_API_KEY=sk-proj-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

---

## MetaOntology 문법 — 핵심 제약

### 9개 공간과 허용 node_type

| space | 허용 node_type |
|-------|---------------|
| subject | person, agent, system, **organization**, role |
| resource | document, dataset, api, **tool**, file, url |
| evidence | log, observation, metric, experiment_result, trace |
| concept | **entity**, abstraction, pattern, theory, keyword |
| claim | assertion, hypothesis, conclusion, finding |
| community | cluster, group, summary, topic, category |
| outcome | kpi, goal, risk, impact, metric_result |
| lever | parameter, config, threshold, flag, weight |
| policy | **rule**, permission, constraint, governance, protocol |

### 주요 허용 관계 (자주 쓰는 것)

| from → to | 허용 관계 |
|-----------|----------|
| subject → resource | owns, manages, created, can_view, can_edit, uses |
| subject → concept | understands, specializes_in, coined |
| subject → subject | knows, reports_to, collaborates_with, is_part_of |
| concept → concept | is_a, part_of, **related_to**, contradicts, extends |
| evidence → claim | supports, contradicts, is_neutral_to |
| concept → resource | described_in, exemplified_by |
| resource → concept | defines, discusses, introduces |
| policy → subject | applies_to, grants, restricts |
| resource → policy | **subject_to** |
| lever → outcome | raises, lowers, optimizes, affects |

**흔한 실수:**
- `concept → concept`: "uses" 불허 → `related_to` 사용
- `resource → policy`: "contains" 불허 → `subject_to` 사용
- `subject → resource`: "maintains" 불허 → `manages` 사용
- space에 없는 node_type (예: "entity"를 subject에, "technology"를 concept에) 사용 금지

`ontology_manifest` 도구로 전체 문법을 항상 확인할 수 있다.

---

## 18개 MCP 도구 요약

| 도구 | 역할 |
|------|------|
| `ping` | 스토어 연결 상태 확인 |
| `ontology_manifest` | 9개 공간·관계·영향 카테고리 전체 문법 반환 |
| `ontology_ingest` | 텍스트 목록 → ChromaDB 저장 |
| `ontology_add_node` | 노드 추가 (space, node_type, node_id, properties) |
| `ontology_add_edge` | 엣지 추가 (from/to space·node_id, relation) |
| `ontology_query` | 하이브리드 검색 (벡터 + BM25 + 그래프 확장) |
| `ontology_extract` | 대용량 텍스트 → LLM 자동 파싱 → 노드·엣지 생성 |
| `query_bm25` | BM25 키워드 검색 (Neo4j 필요) |
| `identity_add_alias` | 노드에 별칭 추가 |
| `identity_resolve` | 별칭으로 노드 조회 |
| `identity_propose_duplicate` | 중복 후보 제안 |
| `identity_resolve_duplicate` | 중복 병합/거부 결정 |
| `workflow_create` | 새 워크플로우 생성 |
| `workflow_advance` | 워크플로우 상태 전진 |
| `workflow_list` | 워크플로우 목록 조회 |
| `impact_record` | 영향 이벤트 기록 (I1~I7 카테고리) |
| `impact_history` | 영향 이력 조회 |
| `harness_run` | PDF/URL 인제스트 파이프라인 실행 |

---

## 테스트 스크립트 구조

```
scripts/
  test_stores.py   — 4개 스토어 개별 CRUD 검증
  test_ontology.py — OntologyBuilder, HybridQuery 검증
  test_mcp.py      — MCP 서버 도구 호출 E2E 검증
  test_phase2.py   — 워크플로우·임팩트·아이덴티티 검증
  test_harness.py  — CrabHarness PDF/URL 파이프라인 검증
  test_all.py      — 위 전체 순서대로 실행
```

---

## 데이터 위치

| 데이터 | 경로 |
|--------|------|
| SQLite DB | `./my_mcp.db` |
| ChromaDB 컬렉션 | `./.chroma/` |
| Neo4j 데이터 | Neo4j Desktop 관리 (별도 볼륨) |
| Neo4j Browser | http://localhost:7474 |

---

## 보안 주의

- `.env`, `.mcp.json` — gitignore됨, **절대 커밋 금지**
- 팀 공유 시 `.mcp.json.example`(비밀번호 플레이스홀더)만 배포
- OpenAI API 키는 `.env`에만 보관, `.mcp.json`에 포함하지 않음

---

## Neo4j 시각화

Neo4j Browser에서 관계 그래프 확인:

```cypher
MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 100
```

노드 속성 필터:
```cypher
MATCH (n {space: "policy"}) RETURN n
```
