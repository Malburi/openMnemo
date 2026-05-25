"""MCP stdio JSON-RPC 2.0 서버."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)

# JSON-RPC 2.0 표준 에러 코드
_ERR_PARSE        = -32700
_ERR_INVALID_REQ  = -32600
_ERR_METHOD_NOT_FOUND = -32601
_ERR_INVALID_PARAMS   = -32602
_ERR_INTERNAL     = -32603

_SERVER_NAME    = "my-mcp"
_SERVER_VERSION = "0.1.0"


def _make_response(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _make_error(req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


class MCPServer:
    """
    stdin/stdout 기반 JSON-RPC 2.0 MCP 서버.

    지원 메서드:
        initialize      — MCP 핸드셰이크
        tools/list      — 사용 가능한 도구 목록 반환
        tools/call      — 도구 실행
        ping            — 서버 상태 확인

    사용 예:
        server = MCPServer()
        server.run()   # stdin 읽기 루프 시작
    """

    def __init__(self) -> None:
        self._ctx: dict | None = None

    def _get_ctx(self) -> dict:
        """컨텍스트 지연 초기화."""
        if self._ctx is None:
            from openmnemo.mcp.context import get_context
            self._ctx = get_context()
        return self._ctx

    # ── 메인 루프 ─────────────────────────────────────────────────────────

    def run(self) -> None:
        """stdin에서 JSON-RPC 요청을 한 줄씩 읽어 처리."""
        # Windows UTF-8 강제 설정
        if sys.platform == "win32":
            import io
            sys.stdin  = io.TextIOWrapper(sys.stdin.buffer,  encoding="utf-8")
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

        logger.info("%s v%s MCP 서버 시작 (stdio)", _SERVER_NAME, _SERVER_VERSION)

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            response = self._handle_raw(line)
            if response is not None:
                self._send(response)

    def _send(self, obj: dict) -> None:
        """JSON 응답을 stdout에 한 줄로 출력."""
        try:
            print(json.dumps(obj, ensure_ascii=False), flush=True)
        except Exception as e:
            logger.error("응답 직렬화 실패: %s", e)

    # ── 요청 처리 ─────────────────────────────────────────────────────────

    def _handle_raw(self, raw: str) -> dict | None:
        """원본 JSON 문자열을 파싱하고 디스패치."""
        try:
            req = json.loads(raw)
        except json.JSONDecodeError as e:
            return _make_error(None, _ERR_PARSE, f"JSON 파싱 오류: {e}")

        # 알림(notification): id 없음 → 응답 없음
        req_id = req.get("id")
        if "id" not in req:
            self._dispatch(req)
            return None

        if req.get("jsonrpc") != "2.0":
            return _make_error(req_id, _ERR_INVALID_REQ, "jsonrpc 버전은 '2.0' 이어야 합니다.")

        method = req.get("method", "")
        if not method:
            return _make_error(req_id, _ERR_INVALID_REQ, "method 필드가 없습니다.")

        return self._dispatch(req)

    def _dispatch(self, req: dict) -> dict | None:
        """메서드를 핸들러로 라우팅."""
        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params") or {}

        handlers = {
            "initialize":   self._handle_initialize,
            "tools/list":   self._handle_tools_list,
            "tools/call":   self._handle_tools_call,
            "ping":         self._handle_ping,
            # 일부 MCP 호스트가 보내는 추가 메서드
            "notifications/initialized": lambda _p, _id: None,
            "$/cancelRequest":           lambda _p, _id: None,
        }

        handler = handlers.get(method)
        if handler is None:
            return _make_error(req_id, _ERR_METHOD_NOT_FOUND, f"알 수 없는 메서드: '{method}'")

        try:
            result = handler(params, req_id)
            if result is None:
                return None
            return _make_response(req_id, result)
        except Exception as e:
            logger.exception("핸들러 오류 (method=%s): %s", method, e)
            return _make_error(req_id, _ERR_INTERNAL, str(e))

    # ── 핸들러 ────────────────────────────────────────────────────────────

    def _handle_initialize(self, params: dict, _req_id: Any) -> dict:
        """MCP 핸드셰이크 응답."""
        client_info = params.get("clientInfo", {})
        logger.info(
            "MCP 클라이언트 연결: %s %s",
            client_info.get("name", "unknown"),
            client_info.get("version", ""),
        )
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name":    _SERVER_NAME,
                "version": _SERVER_VERSION,
            },
            "capabilities": {
                "tools": {"listChanged": False},
            },
        }

    def _handle_tools_list(self, _params: dict, _req_id: Any) -> dict:
        """사용 가능한 도구 목록 반환."""
        from openmnemo.mcp.tools import TOOL_SCHEMAS
        return {"tools": TOOL_SCHEMAS}

    def _handle_tools_call(self, params: dict, _req_id: Any) -> dict:
        """도구 실행."""
        name = params.get("name", "")
        arguments = params.get("arguments") or {}

        if not name:
            raise ValueError("tools/call: name 필드가 없습니다.")

        from openmnemo.mcp.tools import dispatch_tool
        ctx = self._get_ctx()
        result = dispatch_tool(name=name, arguments=arguments, ctx=ctx)

        # MCP 표준 content 형식으로 래핑
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, ensure_ascii=False, indent=2),
                }
            ],
            "isError": "error" in result,
        }

    def _handle_ping(self, _params: dict, _req_id: Any) -> dict:
        return {"status": "ok", "server": _SERVER_NAME, "version": _SERVER_VERSION}


def main() -> None:
    """CLI 진입점."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,   # MCP는 stdout을 JSON 통신에 사용하므로 로그는 stderr
    )
    server = MCPServer()
    server.run()


if __name__ == "__main__":
    main()
