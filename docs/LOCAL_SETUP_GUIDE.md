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

## 12. 18개 MCP 도구 목록

| 카테고리 | 도구명 | 설명 |
|----------|--------|------|
| 기본 | `ping` | 서버·스토어 상태 확인 |
| 기본 | `ontology_manifest` | 온톨로지 문법 조회 |
| 기본 | `ontology_ingest` | 텍스트 벡터 저장 |
| 기본 | `ontology_add_node` | 노드 추가·업데이트 |
| 기본 | `ontology_add_edge` | 노드 간 관계 추가 |
| 기본 | `ontology_query` | 하이브리드 검색 (벡터+그래프) |
| 기본 | `query_bm25` | 키워드 전문 검색 |
| 기본 | `ontology_extract` | 텍스트 → 노드·엣지 자동 추출 |
| Identity | `identity_add_alias` | 노드 별칭 등록 |
| Identity | `identity_resolve` | 별칭 → canonical_id 조회 |
| Identity | `identity_propose_duplicate` | 중복 노드 쌍 제안 |
| Identity | `identity_resolve_duplicate` | 중복 후보 승인·거부 |
| Workflow | `workflow_create` | 워크플로우 생성 |
| Workflow | `workflow_advance` | 상태 전진 |
| Workflow | `workflow_list` | 실행 목록 조회 |
| Impact | `impact_record` | 영향 분석 기록 |
| Impact | `impact_history` | 영향 이력 조회 |
| Harness | `harness_run` | PDF·URL 수집 파이프라인 |
