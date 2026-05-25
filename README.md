# 🦀 my-mcp

**범용 MetaOntology MCP 서버** — OpenMnemo, Claude Code 통합.

9개 공간(Space) 온톨로지에 지식을 축적하고, 18개 MCP 도구로 Claude가 직접 조회·수정·워크플로우 실행을 할 수 있게 합니다.

---

## 목차

- [특징](#특징)
- [아키텍처](#아키텍처)
- [설치](#설치)
- [빠른 시작](#빠른-시작)
- [MCP 도구 레퍼런스](#mcp-도구-레퍼런스)
- [CLI 명령어](#cli-명령어)
- [환경변수](#환경변수)
- [스토어 구성](#스토어-구성)
- [테스트](#테스트)

---

## 특징

| 항목 | 내용 |
|------|------|
| MCP 도구 | **18개** (Phase 1: 8, Phase 2: 10) |
| 온톨로지 공간 | 9개 (subject, resource, evidence, concept, claim, community, outcome, lever, policy) |
| 검색 방식 | 벡터(ChromaDB) + BM25(Neo4j) + 그래프 확장 → RRF 합산 |
| 스토어 | SQLite (항상 사용) + Neo4j / ChromaDB / MongoDB (선택) |
| Harness | PDF·URL → 텍스트 청크 → 검증 → OpenMnemo Pack v1 ZIP |
| 실행 환경 | Python 3.11+, Windows/macOS/Linux |

---

## 아키텍처

```
Claude Code
    │  stdio JSON-RPC 2.0
    ▼
┌─────────────────────────────────────────────┐
│              MCPServer                       │
│   initialize / tools/list / tools/call       │
└──────────────────┬──────────────────────────┘
                   │ dispatch_tool()
         ┌─────────┴──────────┐
         │    18 MCP Tools    │
         └──────┬─────────────┘
       ┌────────┼─────────────┐
       ▼        ▼             ▼
 OntologyBuilder  HybridQuery  IdentityEngine
  Neo4j·Mongo·SQL  Chroma+BM25   node_aliases
                                  duplicates
         ┌────────────────────────────────────┐
         │          CrabHarness               │
         │  Planner → Worker → Validator       │
         │  PdfParser  WebCrawler             │
         │  Promoter → OpenCrab Pack v1 ZIP    │
         └────────────────────────────────────┘
```

---

## 설치

```bash
# 저장소 클론
git clone <repo-url>
cd my-mcp

# 의존성 설치 (uv 권장)
uv sync

# 또는 pip
pip install -e .
```

**선택적 의존성 (bs4 HTML 파싱):**
```bash
pip install beautifulsoup4
```

---

## 빠른 시작

### 1. Claude Code MCP 연결

프로젝트 루트의 `.mcp.json`이 이미 설정되어 있습니다:

```json
{
  "mcpServers": {
    "my-mcp": {
      "command": "python",
      "args": ["-m", "openmnemo.mcp.server"],
      "cwd": "C:/AI_Lab/my-mcp",
      "env": {
        "SQL_URL":     "sqlite:///./my_mcp.db",
        "CHROMA_PATH": "./.chroma",
        "CHROMA_MODE": "local",
        "TENANT_ID":   "default"
      }
    }
  }
}
```

Claude Code를 열면 자동으로 서버가 시작됩니다.

### 2. 연결 확인

Claude Code에서:
```
ping 도구 호출해줘
```

### 3. 텍스트 수집

```
ontology_ingest 도구로 ["RAG는 검색 증강 생성입니다", "pgvector는 벡터 DB 확장입니다"] 저장해줘
```

### 4. 검색

```
ontology_query 도구로 "벡터 저장소" 검색해줘
```

---

## MCP 도구 레퍼런스

### Phase 1 — 기본 (8개)

| 도구 | 설명 |
|------|------|
| `ping` | 서버 상태·스토어 연결 확인 |
| `ontology_manifest` | MetaOntology 전체 문법 반환 |
| `ontology_ingest` | 텍스트 목록 벡터 저장 |
| `ontology_add_node` | 온톨로지 노드 추가/업데이트 |
| `ontology_add_edge` | 노드 간 방향성 관계 추가 |
| `ontology_query` | 하이브리드 검색 (벡터+BM25+그래프) |
| `query_bm25` | 키워드 전문 검색 (Neo4j 필요) |
| `ontology_extract` | 텍스트 → 노드·엣지 자동 추출 |

### Phase 2 — Identity (4개)

| 도구 | 설명 |
|------|------|
| `identity_add_alias` | 노드에 별칭 등록 |
| `identity_resolve` | 별칭 → canonical_id 해석 |
| `identity_propose_duplicate` | 중복 의심 노드 쌍 제안 |
| `identity_resolve_duplicate` | 중복 후보 승인/거부 |

### Phase 2 — Workflow (3개)

| 도구 | 설명 |
|------|------|
| `workflow_create` | 워크플로우 실행 생성 → run_id 반환 |
| `workflow_advance` | 상태 전진 (pending→running→completed) |
| `workflow_list` | 실행 목록 조회 (status 필터 가능) |

### Phase 2 — Impact (2개)

| 도구 | 설명 |
|------|------|
| `impact_record` | 노드 영향 분석 기록 (I1~I7) |
| `impact_history` | 노드 영향 이력 조회 |

### Phase 2 — Harness (1개)

| 도구 | 설명 |
|------|------|
| `harness_run` | PDF·URL → 청크 추출·검증·수집 파이프라인 |

---

## CLI 명령어

```bash
# 서버 시작 (stdio)
my-mcp serve

# 스토어 상태 확인
my-mcp status

# 텍스트 수집
my-mcp ingest "RAG는 검색 증강 생성 기법입니다" --source paper

# 검색
my-mcp query "벡터 저장소" --top-k 5

# MetaOntology 문법 출력
my-mcp manifest

# Harness 실행
my-mcp harness paper.pdf https://example.com --output pack.zip

# 워크플로우
my-mcp workflow list --status pending
my-mcp workflow advance <run-id> running --note "처리 시작"

# Identity
my-mcp identity add-alias rag_system "retrieval augmented generation"
my-mcp identity resolve "retrieval augmented generation"
my-mcp identity duplicates
```

---

## 환경변수

`.env` 파일에 설정합니다:

```env
# SQL (필수 — 미설정 시 SQLite 사용)
SQL_URL=sqlite:///./my_mcp.db

# ChromaDB (로컬 벡터 DB)
CHROMA_MODE=local          # local | http
CHROMA_PATH=./.chroma
CHROMA_HOST=localhost      # http 모드 전용
CHROMA_PORT=8000           # http 모드 전용
CHROMA_COLLECTION=ontology

# Neo4j (선택 — BM25 및 그래프 검색)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

# MongoDB (선택 — 감사 로그)
MONGO_URI=mongodb://localhost:27017
MONGO_DB=my_mcp

# 기타
TENANT_ID=default
RRF_K=60
GRAPH_DEPTH=1
```

---

## 스토어 구성

| 스토어 | 필수 여부 | 역할 |
|--------|----------|------|
| **SQLite** | 필수 | 노드·엣지 레지스트리, 워크플로우, 영향 기록, 정책, 별칭 |
| **ChromaDB** | 권장 | 벡터 임베딩 저장 및 유사도 검색 |
| **Neo4j** | 선택 | BM25 전문 검색, 그래프 탐색 |
| **MongoDB** | 선택 | 노드 상세 문서, 감사 로그 |

Neo4j·MongoDB 없이도 SQLite+ChromaDB 조합으로 동작합니다.

---

## 테스트

```bash
# 전체 통합 테스트
python -X utf8 scripts/test_all.py

# 개별 테스트
python -X utf8 scripts/test_mcp.py      # Phase 1 MCP
python -X utf8 scripts/test_phase2.py   # Phase 2 MCP
python -X utf8 scripts/test_harness.py  # CrabHarness
python -X utf8 scripts/test_stores.py   # 스토어 연결
python -X utf8 scripts/test_ontology.py # 온톨로지 빌더
```

---

## MetaOntology 공간

```
subject    — 사람·에이전트·시스템·조직
resource   — 문서·파일·데이터셋
evidence   — 관찰·실험 결과·로그
concept    — 아이디어·정의·용어
claim      — 주장·가설·명제
community  — 그룹·팀·커뮤니티
outcome    — 결과·영향·산출물
lever      — 개입·정책 수단
policy     — 규칙·제약·거버넌스 정책
```

허용 관계(Relations)는 `my-mcp manifest`로 전체 확인 가능합니다.

---

## 라이선스

MIT
