# openMnemo 로컬 설치 가이드

> 버전: 2025-05-26 | 대상: Windows 11

---

## 개요

openMnemo는 PDF·URL 문서를 지식 그래프로 저장하고 자연어로 검색할 수 있는 MetaOntology MCP 서버입니다.  
Claude Code와 연동하면 채팅으로 문서 등록, 검색, 그래프 조회가 가능합니다.

---

## 1. 사전 요구사항

| 소프트웨어 | 버전 | 설치 확인 |
|-----------|------|-----------|
| Python | 3.11 이상 | `python --version` |
| uv | 최신 | `uv --version` |
| Claude Code | 최신 | 데스크탑 앱 또는 CLI |
| Neo4j Desktop | 1.6.x | winget으로 설치 |

**uv 설치 (없는 경우):**
```powershell
powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Neo4j Desktop 설치:**
```powershell
winget install Neo4j.Neo4jDesktop --accept-package-agreements --accept-source-agreements
```

---

## 2. 프로젝트 설치

```powershell
# 1. 프로젝트 클론 (또는 압축 파일 해제)
cd C:\Users\사용자명
git clone <저장소 URL> openMnemo
cd openMnemo

# 2. 의존성 설치
uv sync
```

설치 완료 시 `.venv` 폴더가 생성됩니다.

---

## 3. Neo4j 데이터베이스 설정

### 3-1. Neo4j Desktop 실행 및 DB 생성

1. 시작 메뉴에서 **Neo4j Desktop** 실행
2. **+ New → Create project** 클릭
3. 프로젝트 내 **+ Add → Local DBMS** 클릭
4. Name: 원하는 이름 (예: `openMnemo`)
5. Password: 비밀번호 입력 후 기록해 둘 것
6. **Create → Start** 클릭 (녹색 ACTIVE 표시 확인)

> **주의**: 기본 사용자명은 항상 `neo4j`입니다. 별도 변경하지 마세요.

---

## 4. 환경 변수 설정 (.env)

프로젝트 루트의 `.env` 파일을 열어 아래와 같이 설정합니다.

```env
# ── Neo4j ──────────────────────────────────────────
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=여기에_설정한_비밀번호

# ── MongoDB ────────────────────────────────────────
MONGO_URI=
MONGO_DB=my_mcp

# ── SQL ────────────────────────────────────────────
SQL_URL=sqlite:///./my_mcp.db

# ── ChromaDB ───────────────────────────────────────
CHROMA_MODE=local
CHROMA_PATH=./.chroma

# ── 임베딩 ─────────────────────────────────────────
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

> `MONGO_URI`는 비워두면 비활성화됩니다 (MongoDB 없어도 동작).

---

## 5. MCP 서버 설정 (.mcp.json)

프로젝트 루트의 `.mcp.json`을 열어 경로와 비밀번호를 본인 환경에 맞게 수정합니다.

```json
{
  "mcpServers": {
    "my-mcp": {
      "command": "C:\\Users\\사용자명\\openMnemo\\.venv\\Scripts\\python.exe",
      "args": ["-m", "openmnemo.mcp.server"],
      "cwd": "C:/Users/사용자명/openMnemo",
      "env": {
        "SQL_URL":        "sqlite:///./my_mcp.db",
        "CHROMA_PATH":    "./.chroma",
        "CHROMA_MODE":    "local",
        "NEO4J_URI":      "bolt://localhost:7687",
        "NEO4J_USER":     "neo4j",
        "NEO4J_PASSWORD": "여기에_설정한_비밀번호",
        "MONGO_URI":      "",
        "TENANT_ID":      "default"
      }
    }
  }
}
```

> **핵심**: `.env`와 `.mcp.json` 두 곳 모두 같은 비밀번호를 입력해야 합니다.

---

## 6. 연결 확인

### 6-1. CLI로 확인
```powershell
cd C:\Users\사용자명\openMnemo
uv run my-mcp status
```

정상 출력:
```
  NEO4J      ✅ 연결됨
  CHROMA     ✅ 연결됨
  MONGO      미설정
  SQL        ✅ 연결됨
```

### 6-2. Claude Code에서 확인

1. Claude Code를 **openMnemo 폴더**에서 열기
2. `.mcp.json` 자동 로드 후 채팅창에 입력:

```
ping 도구 호출해줘
```

응답 예시:
```json
{"status": "ok", "stores": {"neo4j": "ok", "chroma": "ok"}, "tool_count": 18}
```

> **주의**: `.mcp.json` 수정 후에는 반드시 Claude Code를 재시작해야 반영됩니다.

---

## 7. 기본 사용법

### 7-1. PDF 등록

```
harness_run 도구로 sources=["C:/Users/사용자명/문서/파일.pdf"] 처리해줘
```

### 7-2. 검색

```
ontology_query 도구로 "검색어" 검색해줘
```

### 7-3. 노드 직접 추가

```
ontology_add_node 도구로 space="concept", node_id="my_concept", node_type="abstraction",
properties={"label": "내 개념", "description": "설명"} 추가해줘
```

### 7-4. 관계 추가

```
ontology_add_edge 도구로 from_space="concept", from_id="a", to_space="concept", to_id="b",
relation="related_to" 추가해줘
```

### 7-5. CLI 사용

```powershell
uv run my-mcp ingest "저장할 텍스트" --source 출처명
uv run my-mcp query "검색어" --top-k 5
uv run my-mcp harness C:/path/to/file.pdf
uv run my-mcp status
```

---

## 8. Neo4j 그래프 시각화

브라우저에서 `http://localhost:7474` 접속 후 로그인하면 Cypher 쿼리로 그래프를 볼 수 있습니다.

```cypher
-- 전체 그래프 보기
MATCH (n)-[r]->(m) RETURN n, r, m

-- 특정 노드 검색
MATCH (n) WHERE n.label CONTAINS '검색어' RETURN n

-- 연결 관계 깊이 탐색
MATCH path = (n)-[*1..3]->(m) WHERE n.node_id = 'my_node' RETURN path
```

---

## 9. 허용 노드 타입 및 관계

### 공간별 허용 node_type

| space | 허용 node_type |
|-------|----------------|
| `concept` | entity, abstraction, pattern, theory, keyword |
| `subject` | person, agent, system, organization, role |
| `resource` | document, dataset, api, tool, file, url |
| `evidence` | observation, experiment, log, measurement |
| `claim` | hypothesis, assertion, finding, opinion |
| `community` | group, team, forum, network |
| `outcome` | result, impact, product, artifact |
| `lever` | intervention, mechanism, strategy |
| `policy` | rule, regulation, constraint, guideline |

### 주요 공간 간 허용 relation

| from → to | 허용 relation |
|-----------|---------------|
| concept → concept | is_a, part_of, related_to, contradicts, extends |
| subject → concept | understands, specializes_in, coined |
| subject → resource | owns, manages, created, can_view, can_edit, uses |
| resource → policy | subject_to |
| subject → policy | governed_by, enforces, proposes |

---

## 10. 문제 해결

### MCP 도구가 안 보일 때
→ Claude Code를 **완전히 종료 후 재시작**. openMnemo 폴더에서 열었는지 확인.

### neo4j: not_configured 가 뜰 때
→ `.mcp.json`의 `NEO4J_PASSWORD` 값 확인. 대소문자 구분됩니다.  
→ Neo4j Desktop에서 DB가 **ACTIVE** 상태인지 확인.

### 포트 오류
→ Neo4j Bolt 포트는 **7687** (브라우저 포트 7474와 다름)

### 임베딩 오류
→ `.env`의 `OPENAI_API_KEY` 확인

### 패키지 재설치
```powershell
cd C:\Users\사용자명\openMnemo
Remove-Item -Recurse -Force .venv
uv sync
```

---

## 11. 데이터 저장 위치

| 스토어 | 경로 | 역할 |
|--------|------|------|
| SQLite | `openMnemo\my_mcp.db` | 노드·엣지·워크플로우 |
| ChromaDB | `openMnemo\.chroma\` | 벡터 임베딩 (검색용) |
| Neo4j | Neo4j Desktop 내부 | 그래프 관계 |

---

## 12. 18개 MCP 도구 상세 가이드

> 모든 도구는 Claude Code 채팅창에서 자연어로 호출합니다.

---

### 기본 도구

---

#### `ping` — 서버·스토어 상태 확인

서버가 정상 동작 중인지, 각 스토어(Neo4j, ChromaDB, SQL)에 연결됐는지 확인합니다.

**사용 예:**
```
ping 도구 호출해줘
```

**응답 예시:**
```json
{
  "status": "ok",
  "stores": { "neo4j": "ok", "chroma": "ok", "mongo": "not_configured", "sql": "ok" },
  "identity": "ok",
  "tool_count": 18,
  "table_counts": { "ontology_nodes": 14, "ontology_edges": 11 }
}
```

---

#### `ontology_manifest` — 온톨로지 문법 전체 조회

9개 공간 정의, 허용 관계, 영향 카테고리 전체를 JSON으로 반환합니다.

**사용 예:**
```
ontology_manifest 도구로 문법 전체 보여줘
```

**CLI:**
```powershell
uv run my-mcp manifest
```

---

#### `ontology_ingest` — 텍스트 벡터 저장

텍스트를 임베딩 벡터로 변환해 ChromaDB에 저장합니다. `ontology_query`로 검색 가능해집니다.

**사용 예:**
```
ontology_ingest 도구로 다음 텍스트들을 저장해줘:
- "RAG는 검색 증강 생성 기법이다"
- "ChromaDB는 벡터 데이터베이스다"
```

**파라미터:**
| 파라미터 | 필수 | 설명 |
|----------|------|------|
| `texts` | ✅ | 저장할 텍스트 목록 |
| `metadatas` | ❌ | 각 텍스트의 메타데이터 (space, node_id 등) |
| `ids` | ❌ | 고유 ID (미지정 시 SHA256 자동 생성) |

**CLI:**
```powershell
uv run my-mcp ingest "저장할 텍스트" --source 출처명
```

---

#### `ontology_add_node` — 노드 추가·업데이트

온톨로지 그래프에 노드를 추가합니다. 같은 `node_id`로 재호출하면 업데이트됩니다.

**사용 예:**
```
ontology_add_node 도구로
  space="concept", node_id="machine_learning", node_type="abstraction",
  properties={"label": "머신러닝", "description": "데이터로부터 패턴을 학습하는 기술"}
추가해줘
```

**파라미터:**
| 파라미터 | 필수 | 설명 |
|----------|------|------|
| `space` | ✅ | 9개 공간 중 하나 |
| `node_id` | ✅ | 고유 ID (snake_case 권장) |
| `node_type` | ❌ | 공간별 허용 타입 (아래 표 참고) |
| `properties` | ❌ | label, description 등 속성 |

> **공간별 허용 node_type** → 9절 참고

---

#### `ontology_add_edge` — 노드 간 관계 추가

두 노드 사이에 방향성 관계를 추가합니다.

**사용 예:**
```
ontology_add_edge 도구로
  from_space="subject", from_id="openai",
  to_space="concept", to_id="embedding",
  relation="specializes_in"
추가해줘
```

**파라미터:**
| 파라미터 | 필수 | 설명 |
|----------|------|------|
| `from_space` | ✅ | 출발 노드의 공간 |
| `from_id` | ✅ | 출발 노드 ID |
| `to_space` | ✅ | 도착 노드의 공간 |
| `to_id` | ✅ | 도착 노드 ID |
| `relation` | ✅ | 관계 레이블 (공간 조합별 허용 목록 있음) |
| `properties` | ❌ | 관계 속성 |

> **공간 간 허용 relation** → 9절 참고

---

#### `ontology_query` — 하이브리드 검색

자연어 쿼리로 벡터 유사도 + 그래프 확장을 결합해 검색합니다.

**사용 예:**
```
ontology_query 도구로 "경조금 지급 기준" 검색해줘
ontology_query 도구로 "머신러닝" top_k=10으로 검색해줘
```

**파라미터:**
| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `query` | — | 검색할 자연어 쿼리 |
| `top_k` | 5 | 반환할 최대 결과 수 |
| `source_filter` | — | 특정 소스만 검색 (파일명 등) |
| `min_score` | 0.0 | 최소 점수 임계값 (0.0~1.0) |
| `use_graph` | true | 그래프 확장 사용 여부 |

**CLI:**
```powershell
uv run my-mcp query "검색어" --top-k 10
uv run my-mcp query "검색어" --no-graph
```

---

#### `query_bm25` — 키워드 전문 검색

정확한 단어·고유명사 검색에 적합합니다. Neo4j 연결 필요.

**사용 예:**
```
query_bm25 도구로 "복리후생" 키워드 검색해줘
```

**파라미터:**
| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `query` | — | 검색 키워드 |
| `top_k` | 10 | 최대 결과 수 |
| `source_filter` | — | 특정 소스 필터 |

---

#### `ontology_extract` — 텍스트 → 노드·엣지 자동 추출

텍스트에서 개념·주체·자원을 자동으로 파악해 노드와 엣지로 저장합니다.

**사용 예:**
```
ontology_extract 도구로 다음 텍스트에서 개념을 추출해줘:
"RAG 시스템은 ChromaDB를 벡터 스토어로 사용하며, OpenAI 임베딩을 통해 문서를 저장한다."
source="rag_description"으로 설정해줘
```

**파라미터:**
| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `text` | — | 추출할 텍스트 |
| `source` | "unknown" | 출처 식별자 |
| `auto_ingest` | true | 추출 후 벡터 스토어 자동 저장 |

---

### Identity 도구

---

#### `identity_add_alias` — 노드 별칭 등록

하나의 노드에 여러 이름(별칭)을 등록합니다.

**사용 예:**
```
identity_add_alias 도구로
  canonical_id="rag", alias="검색증강생성", space="concept"
등록해줘
```

---

#### `identity_resolve` — 별칭으로 canonical_id 조회

별칭을 입력하면 연결된 원본 노드 ID를 반환합니다.

**사용 예:**
```
identity_resolve 도구로 "검색증강생성" 조회해줘
```

**CLI:**
```powershell
uv run my-mcp identity resolve "검색증강생성"
```

---

#### `identity_propose_duplicate` — 중복 노드 쌍 제안

두 노드가 같은 개념을 가리킬 가능성이 있을 때 검토 대상으로 등록합니다. 자동 병합은 하지 않습니다.

**사용 예:**
```
identity_propose_duplicate 도구로
  node_a="rag", node_b="retrieval_augmented_generation",
  space="concept", reason="같은 개념의 다른 표기"
제안해줘
```

---

#### `identity_resolve_duplicate` — 중복 후보 승인·거부

`identity_propose_duplicate`로 등록된 중복 후보를 승인하거나 거부합니다.

**사용 예:**
```
identity_resolve_duplicate 도구로
  candidate_id="<ID>", action="approve"
처리해줘
```

**CLI:**
```powershell
uv run my-mcp identity duplicates          # 목록 조회
```

---

### Workflow 도구

---

#### `workflow_create` — 워크플로우 생성

장기 작업(수집, 검토, 배포 등)을 추적하는 실행 단위를 생성합니다.

**사용 예:**
```
workflow_create 도구로
  action_type="ingest", payload={"source": "규정집.pdf"}
워크플로우 만들어줘
```

**상태 흐름:** `pending → running → completed / failed`

---

#### `workflow_advance` — 워크플로우 상태 전진

워크플로우의 상태를 다음 단계로 변경합니다.

**사용 예:**
```
workflow_advance 도구로
  run_id="<ID>", new_status="running", note="처리 시작"
실행해줘
```

---

#### `workflow_list` — 실행 목록 조회

워크플로우 실행 목록을 조회합니다.

**사용 예:**
```
workflow_list 도구로 pending 상태 목록 보여줘
workflow_list 도구로 전체 목록 20개 보여줘
```

**CLI:**
```powershell
uv run my-mcp workflow list --status pending
uv run my-mcp workflow list --limit 50
```

---

### Impact 도구

---

#### `impact_record` — 영향 분석 기록

노드에 발생한 영향을 카테고리별로 기록합니다.

**사용 예:**
```
impact_record 도구로
  node_id="rag", space="concept", category="I6",
  result={"description": "새로운 RAG 패턴 발견", "score": 0.9}
기록해줘
```

**영향 카테고리:**
| 카테고리 | 설명 |
|----------|------|
| `I1` | 데이터 변화 |
| `I2` | 워크플로우 변화 |
| `I3` | 주체 행동 변화 |
| `I4` | 커뮤니티 효과 |
| `I5` | 거버넌스 변화 |
| `I6` | 지식 생성 |
| `I7` | 감사·추적 |

---

#### `impact_history` — 영향 이력 조회

특정 노드의 영향 분석 기록 전체를 조회합니다.

**사용 예:**
```
impact_history 도구로 node_id="rag" 이력 조회해줘
```

---

### Harness 도구

---

#### `harness_run` — PDF·URL 수집 파이프라인

PDF 파일 또는 웹 URL을 자동으로 파싱·청킹·검증 후 온톨로지에 저장합니다.

**사용 예:**
```
harness_run 도구로 sources=["C:/Users/사용자명/문서/규정집.pdf"] 처리해줘
harness_run 도구로 sources=["https://example.com/article"] 처리해줘
harness_run 도구로 sources=["C:/file1.pdf", "https://example.com"] 처리해줘
```

**파라미터:**
| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `sources` | — | PDF 경로 또는 URL 목록 |
| `goal` | "ingest" | Mission 목표 |
| `auto_ingest` | true | 검증 통과 청크 벡터 저장 여부 |

**처리 흐름:**
```
소스 입력 → Worker(PDF파서/웹크롤러) → 청크 분할 → 검증 → ChromaDB + Neo4j 저장
```

**응답 예시:**
```json
{
  "total_sources": 1,
  "passed": 1,
  "failed": 0,
  "jobs": [{ "worker": "pdf_parser", "worker_score": 0.995 }]
}
```

**CLI:**
```powershell
uv run my-mcp harness "C:/path/to/file.pdf" --output result.zip
uv run my-mcp harness https://example.com
```
