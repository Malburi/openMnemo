"""my-mcp CLI 진입점."""

from __future__ import annotations

import json
import sys

import click


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(".env")
    except ImportError:
        pass


@click.group()
def main() -> None:
    """my-mcp — 범용 MetaOntology MCP 서버."""


# ── serve ─────────────────────────────────────────────────────────────────────

@main.command()
def serve() -> None:
    """MCP 서버를 stdio 모드로 시작합니다."""
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    from openmnemo.mcp.server import MCPServer
    click.echo("🦀 my-mcp MCP 서버 시작 (stdin/stdout JSON-RPC 2.0)", err=True)
    MCPServer().run()


# ── status ────────────────────────────────────────────────────────────────────

@main.command()
def status() -> None:
    """스토어 연결 상태를 확인합니다."""
    _load_env()
    from openmnemo.mcp.context import get_context

    click.echo("스토어 연결 상태 확인 중...")
    ctx = get_context()

    rows = []
    for name in ("neo4j", "chroma", "mongo", "sql"):
        store = ctx.get(name)
        if store is None:
            s = click.style("미설정", fg="yellow")
        else:
            try:
                s = click.style("✅ 연결됨", fg="green") if store.ping() \
                    else click.style("❌ 연결 실패", fg="red")
            except Exception as e:
                s = click.style(f"❌ 오류: {e}", fg="red")
        rows.append((name.upper(), s))

    click.echo("")
    for name, s in rows:
        click.echo(f"  {name:<10} {s}")

    # SQL 테이블 카운트 요약
    sql = ctx.get("sql")
    if sql:
        try:
            counts = sql.table_counts()
            click.echo("\n  SQL 테이블:")
            for t, n in counts.items():
                click.echo(f"    {t:<22} {n:>6}건")
        except Exception:
            pass
    click.echo("")


# ── query ─────────────────────────────────────────────────────────────────────

@main.command()
@click.argument("query_text")
@click.option("--top-k", "-k", default=5, help="반환할 최대 결과 수")
@click.option("--no-graph", is_flag=True, default=False, help="그래프 확장 비활성화")
def query(query_text: str, top_k: int, no_graph: bool) -> None:
    """자연어 쿼리로 온톨로지를 검색합니다."""
    _load_env()
    from openmnemo.mcp.context import get_context
    from openmnemo.mcp.tools import dispatch_tool

    ctx = get_context()
    result = dispatch_tool(
        name="ontology_query",
        arguments={"query": query_text, "top_k": top_k, "use_graph": not no_graph},
        ctx=ctx,
    )

    if "error" in result:
        click.echo(click.style(f"오류: {result['error']}", fg="red"), err=True)
        sys.exit(1)

    click.echo(f"\n쿼리: {result['query']}")
    click.echo(f"결과: {result['count']}건\n")
    for r in result["results"]:
        score = r["score"]
        color = "green" if score >= 0.7 else "yellow" if score >= 0.4 else "white"
        click.echo(
            click.style(f"  [{r['source']}] score={score:.3f}", fg=color)
            + f"  {r['text'][:80]}"
        )
    click.echo("")


# ── ingest ────────────────────────────────────────────────────────────────────

@main.command()
@click.argument("text")
@click.option("--source", "-s", default="cli_input", help="텍스트 출처 식별자")
def ingest(text: str, source: str) -> None:
    """텍스트를 온톨로지에 수집·저장합니다."""
    _load_env()
    from openmnemo.mcp.context import get_context
    from openmnemo.mcp.tools import dispatch_tool

    ctx = get_context()
    result = dispatch_tool(
        name="ontology_extract",
        arguments={"text": text, "source": source, "auto_ingest": True},
        ctx=ctx,
    )

    if "error" in result:
        click.echo(click.style(f"오류: {result['error']}", fg="red"), err=True)
        sys.exit(1)

    click.echo(f"\n수집 완료:")
    click.echo(f"  소스:       {result['source']}")
    click.echo(f"  청크:       {result['chunks']}개")
    click.echo(f"  노드 추가:  {result['nodes_added']}개")
    click.echo(f"  엣지 추가:  {result['edges_added']}개")
    click.echo(f"  벡터 저장:  {result['vector_ids']}개\n")


# ── manifest ──────────────────────────────────────────────────────────────────

@main.command()
def manifest() -> None:
    """MetaOntology 문법 전체를 출력합니다."""
    from openmnemo.grammar.glossary import full_glossary
    click.echo(json.dumps(full_glossary(), ensure_ascii=False, indent=2))


# ── harness ───────────────────────────────────────────────────────────────────

@main.command()
@click.argument("sources", nargs=-1, required=True)
@click.option("--output", "-o", default=None, help="ZIP 출력 경로 (미지정 시 임시 파일)")
@click.option("--no-ingest", is_flag=True, default=False, help="벡터 스토어 저장 건너뜀")
def harness(sources: tuple[str, ...], output: str | None, no_ingest: bool) -> None:
    """소스(PDF 경로 또는 URL)를 CrabHarness로 처리합니다."""
    _load_env()
    import tempfile
    from crabharness.harness import CrabHarness
    from crabharness.planner import Mission

    if output is None:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
            output = f.name

    click.echo(f"\n🦀 CrabHarness 실행 — {len(sources)}개 소스")
    mission = Mission(sources=list(sources), goal="ingest")
    result  = CrabHarness().run(mission, output_path=output)

    click.echo(f"\n결과:")
    click.echo(f"  총 소스:    {len(result.jobs)}개")
    click.echo(f"  검증 합격:  {result.passed_count}개")
    click.echo(f"  검증 실패:  {result.failed_count}개")

    for rp in result.reports:
        color = "green" if rp.passed else "red"
        mark  = "✅" if rp.passed else "❌"
        click.echo(
            click.style(f"  {mark} [{rp.space}] ", fg=color)
            + f"{rp.source[:60]}"
            + (f" — {', '.join(rp.issues)}" if rp.issues else "")
        )

    if result.pack and result.pack.included_count > 0:
        click.echo(f"\n  Pack 저장: {result.pack.path}")
        click.echo(f"  포함 소스: {result.pack.included_count}개\n")

    if result.errors:
        for err in result.errors:
            click.echo(click.style(f"  ⚠ {err}", fg="yellow"))
    click.echo("")


# ── workflow ──────────────────────────────────────────────────────────────────

@main.group()
def workflow() -> None:
    """워크플로우 실행 관리."""


@workflow.command("list")
@click.option("--status", "-s", default=None, help="상태 필터 (pending/running/completed/failed)")
@click.option("--limit", "-n", default=20, help="최대 표시 수")
def workflow_list(status: str | None, limit: int) -> None:
    """워크플로우 실행 목록을 조회합니다."""
    _load_env()
    from openmnemo.mcp.context import get_context

    ctx = get_context()
    sql = ctx.get("sql")
    if not sql:
        click.echo(click.style("SQL 스토어 없음", fg="red"), err=True)
        sys.exit(1)

    runs = sql.list_runs(status=status, limit=limit)
    if not runs:
        click.echo("  (실행 없음)")
        return

    click.echo(f"\n{'run_id':<38} {'action_type':<14} {'status':<12} {'created_at'}")
    click.echo("-" * 90)
    for r in runs:
        color = {"pending": "yellow", "running": "cyan",
                 "completed": "green", "failed": "red"}.get(r["status"], "white")
        click.echo(
            f"  {r['run_id']:<36} {r['action_type']:<14} "
            + click.style(f"{r['status']:<12}", fg=color)
            + f" {r['created_at'][:19]}"
        )
    click.echo("")


@workflow.command("advance")
@click.argument("run_id")
@click.argument("new_status")
@click.option("--note", "-n", default="", help="변경 사유")
@click.option("--actor", "-a", default="cli", help="변경 주체")
def workflow_advance(run_id: str, new_status: str, note: str, actor: str) -> None:
    """워크플로우 상태를 전진시킵니다."""
    _load_env()
    from openmnemo.mcp.context import get_context

    ctx = get_context()
    sql = ctx.get("sql")
    if not sql:
        click.echo(click.style("SQL 스토어 없음", fg="red"), err=True)
        sys.exit(1)

    updated = sql.advance_run(run_id=run_id, new_status=new_status, note=note, actor=actor)
    if updated:
        click.echo(click.style(f"✅ {run_id[:12]}... → {new_status}", fg="green"))
    else:
        click.echo(click.style(f"❌ 업데이트 실패: run_id를 확인하세요.", fg="red"))
        sys.exit(1)


# ── identity ──────────────────────────────────────────────────────────────────

@main.group()
def identity() -> None:
    """노드 별칭 및 중복 후보 관리."""


@identity.command("resolve")
@click.argument("alias")
def identity_resolve(alias: str) -> None:
    """별칭으로 canonical node_id를 조회합니다."""
    _load_env()
    from openmnemo.mcp.context import get_context

    ctx = get_context()
    eng = ctx.get("identity")
    if not eng:
        click.echo(click.style("IdentityEngine 없음", fg="red"), err=True)
        sys.exit(1)

    canonical = eng.resolve_canonical(alias)
    if canonical:
        click.echo(f"  {alias!r}  →  {click.style(canonical, fg='green')}")
    else:
        click.echo(click.style(f"  별칭 없음: {alias!r}", fg="yellow"))


@identity.command("add-alias")
@click.argument("canonical_id")
@click.argument("alias")
@click.option("--space", "-s", default="concept", help="노드 공간")
def identity_add_alias(canonical_id: str, alias: str, space: str) -> None:
    """노드에 별칭을 등록합니다."""
    _load_env()
    from openmnemo.mcp.context import get_context

    ctx = get_context()
    eng = ctx.get("identity")
    if not eng:
        click.echo(click.style("IdentityEngine 없음", fg="red"), err=True)
        sys.exit(1)

    eng.add_alias(canonical_id=canonical_id, alias=alias, space=space)
    click.echo(click.style(f"✅ '{alias}' → '{canonical_id}' 등록 완료", fg="green"))


@identity.command("duplicates")
@click.option("--space", "-s", default=None, help="공간 필터")
def identity_duplicates(space: str | None) -> None:
    """대기 중인 중복 후보 목록을 조회합니다."""
    _load_env()
    from openmnemo.mcp.context import get_context

    ctx = get_context()
    eng = ctx.get("identity")
    if not eng:
        click.echo(click.style("IdentityEngine 없음", fg="red"), err=True)
        sys.exit(1)

    candidates = eng.list_pending_duplicates(space=space)
    if not candidates:
        click.echo("  (대기 중인 중복 후보 없음)")
        return

    click.echo(f"\n  {'candidate_id':<34} {'node_a':<20} {'node_b':<20} {'reason'}")
    click.echo("-" * 90)
    for c in candidates:
        click.echo(
            f"  {c['candidate_id'][:32]:<34} "
            f"{c['node_a']:<20} {c['node_b']:<20} {c.get('reason','')}"
        )
    click.echo("")


if __name__ == "__main__":
    main()
