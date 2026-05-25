# my-mcp 사용자 매뉴얼

## 전체 흐름

```
1. Claude Code 설치 및 열기
2. C:\AI_Lab\my-mcp 폴더 열기
3. Claude Code가 자동으로 MCP 서버 시작
4. Claude에게 말로 요청 → MCP 도구 실행
```

---

## STEP 1 — 사전 준비 확인

터미널에서 패키지가 설치되었는지 확인합니다.

```powershell
cd C:\AI_Lab\my-mcp

"C:\AI_Lab\AX-AILab2-2-main\.venv\Scripts\python.exe" -c "import openmnemo; print('OK')"
```

`OK` 가 출력되면 준비 완료입니다.

---

## STEP 2 — Claude Code MCP 연결

Claude Code(데스크탑 앱 또는 IDE 플러그인)를 **`C:\AI_Lab\my-mcp` 폴더**에서 열어야 합니다.

**데스크탑 앱 기준:**

1. Claude Code 앱 실행
2. `File → Open Folder` → `C:\AI_Lab\my-mcp` 선택
3. 폴더가 열리면 `.mcp.json`을 자동으로 읽어 서버 시작

**연결 확인:**

Claude Code 채팅창에 입력합니다.

```
ping 도구 호출해줘
```

아래와 비슷한 응답이 오면 연결 성공입니다.

```json
{"status": "ok", "version": "0.1.0", "tools": 18, ...}
```

---

## STEP 3 — 주요 기능 사용법

### 지식 저장

```
ontology_ingest 도구로 다음 텍스트들을 저장해줘:
- "RAG는 검색 증강 생성 기법이다"
- "ChromaDB는 벡터 데이터베이스이다"
```

### 검색

```
ontology_query 도구로 "벡터 저장소"를 검색해줘
```

### 노드 추가 (그래프)

```
ontology_add_node 도구로
  space="concept", node_id="rag", label="RAG 시스템", description="검색 증강 생성"
노드를 추가해줘
```

### 관계 추가

```
ontology_add_edge 도구로 from_id="rag", to_id="chromadb", relation="uses" 엣지 추가해줘
```

### PDF / URL 수집

```
harness_run 도구로 sources=["https://example.com"] 처리해줘
```

로컬 PDF 파일도 가능합니다.

```
harness_run 도구로 sources=["C:/Users/me/paper.pdf"] 처리해줘
```

### 워크플로우

```
# 생성
workflow_create 도구로 action_type="ingest", payload={"source": "test.pdf"} 워크플로우 만들어줘

# 목록 조회
workflow_list 도구로 pending 상태 목록 보여줘

# 상태 전진
workflow_advance 도구로 run_id="<ID>", new_status="running", note="처리 시작" 실행해줘
```

### 별칭(Identity) 관리

```
# 별칭 등록
identity_add_alias 도구로 canonical_id="rag_system", alias="검색증강생성", space="concept" 등록해줘

# 별칭 조회
identity_resolve 도구로 "검색증강생성" 조회해줘
```

### 영향 분석

```
# 기록
impact_record 도구로 node_id="rag_system", space="concept", category="I6",
  result={"description": "지식 생성 영향", "score": 0.85} 기록해줘

# 이력 조회
impact_history 도구로 node_id="rag_system" 이력 조회해줘
```

---

## STEP 4 — CLI 직접 사용

Claude Code 없이 터미널에서 직접 실행할 수도 있습니다.

```powershell
# 별칭 지정 (선택)
Set-Alias mnemo "C:\AI_Lab\AX-AILab2-2-main\.venv\Scripts\python.exe"

# 서버 상태
python -m openmnemo.cli status

# 텍스트 저장
python -m openmnemo.cli ingest "RAG는 검색 증강 생성입니다" --source paper

# 검색
python -m openmnemo.cli query "벡터 저장소" --top-k 5

# 온톨로지 문법 확인
python -m openmnemo.cli manifest

# Harness 실행
python -m openmnemo.cli harness paper.pdf https://example.com --output pack.zip

# 워크플로우 목록
python -m openmnemo.cli workflow list --status pending

# Identity 별칭 등록
python -m openmnemo.cli identity add-alias rag_system "retrieval augmented generation"
```

---

## STEP 5 — 문제 해결

### MCP 도구가 안 보일 때

**원인**: Claude Code가 `.mcp.json`의 Python 경로를 찾지 못하는 경우

**확인**:

```powershell
cat C:\AI_Lab\my-mcp\.mcp.json
```

`"command"` 값이 아래와 같아야 합니다.

```json
"command": "C:\\AI_Lab\\AX-AILab2-2-main\\.venv\\Scripts\\python.exe"
```

**조치**:

1. Claude Code를 완전히 종료
2. `C:\AI_Lab\my-mcp` 폴더에서 다시 열기

---

### 서버 직접 테스트

Claude Code 없이 서버가 정상 시작되는지 확인합니다.

```powershell
cd C:\AI_Lab\my-mcp
"C:\AI_Lab\AX-AILab2-2-main\.venv\Scripts\python.exe" -m openmnemo.mcp.server
```

`my-mcp v0.1.0 MCP 서버 시작 (stdio)` 메시지가 뜨면 서버는 정상입니다. `Ctrl+C`로 종료합니다.

---

### 테스트 스크립트 실행

```powershell
cd C:\AI_Lab\my-mcp

# Phase 1 테스트 (기본 8개 도구)
"C:\AI_Lab\AX-AILab2-2-main\.venv\Scripts\python.exe" -X utf8 scripts/test_mcp.py

# Phase 2 테스트 (신규 10개 도구)
"C:\AI_Lab\AX-AILab2-2-main\.venv\Scripts\python.exe" -X utf8 scripts/test_phase2.py

# 전체 통합 테스트
"C:\AI_Lab\AX-AILab2-2-main\.venv\Scripts\python.exe" -X utf8 scripts/test_all.py
```

---

### 패키지 재설치

```powershell
cd C:\AI_Lab\my-mcp
"C:\AI_Lab\AX-AILab2-2-main\.venv\Scripts\python.exe" -m pip install -e .
```

---

## 18개 도구 전체 목록

| 카테고리 | 도구명 | 역할 |
|----------|--------|------|
| 기본 | `ping` | 서버/스토어 상태 확인 |
| 기본 | `ontology_manifest` | 온톨로지 문법 조회 |
| 기본 | `ontology_ingest` | 텍스트 일괄 저장 |
| 기본 | `ontology_add_node` | 노드 추가/업데이트 |
| 기본 | `ontology_add_edge` | 노드 간 관계 추가 |
| 기본 | `ontology_query` | 하이브리드 검색 (벡터+BM25+그래프) |
| 기본 | `query_bm25` | 키워드 전문 검색 (Neo4j 필요) |
| 기본 | `ontology_extract` | 텍스트 → 노드/엣지 자동 추출 |
| Identity | `identity_add_alias` | 노드 별칭 등록 |
| Identity | `identity_resolve` | 별칭 → canonical_id 조회 |
| Identity | `identity_propose_duplicate` | 중복 의심 노드 쌍 제안 |
| Identity | `identity_resolve_duplicate` | 중복 후보 승인/거부 |
| Workflow | `workflow_create` | 워크플로우 실행 생성 |
| Workflow | `workflow_advance` | 상태 전진 (pending→running→completed) |
| Workflow | `workflow_list` | 실행 목록 조회 |
| Impact | `impact_record` | 노드 영향 분석 기록 (I1~I7) |
| Impact | `impact_history` | 노드 영향 이력 조회 |
| Harness | `harness_run` | PDF/URL → 청크 수집 파이프라인 |

---

## 온톨로지 9개 공간 (Space)

| Space | 의미 |
|-------|------|
| `subject` | 사람·에이전트·시스템·조직 |
| `resource` | 문서·파일·데이터셋 |
| `evidence` | 관찰·실험 결과·로그 |
| `concept` | 아이디어·정의·용어 |
| `claim` | 주장·가설·명제 |
| `community` | 그룹·팀·커뮤니티 |
| `outcome` | 결과·영향·산출물 |
| `lever` | 개입·정책 수단 |
| `policy` | 규칙·제약·거버넌스 정책 |

허용 관계 전체 목록은 `ontology_manifest` 도구로 확인할 수 있습니다.

---

## 데이터 저장 위치

| 스토어 | 경로 / 주소 | 역할 |
|--------|------------|------|
| SQLite | `C:\AI_Lab\my-mcp\my_mcp.db` | 노드·엣지·워크플로우·별칭 |
| ChromaDB | `C:\AI_Lab\my-mcp\.chroma\` | 벡터 임베딩 |
| Neo4j | `bolt://localhost:7687` (선택) | BM25·그래프 검색 |
| MongoDB | `mongodb://localhost:27017` (선택) | 감사 로그 |

Neo4j·MongoDB 없이 SQLite + ChromaDB 조합으로 동작합니다.
