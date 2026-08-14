#!/usr/bin/env python3
"""측정용 최소 MCP stdio 서버. 도구 1개만 알린다.

두 가지를 남긴다:
  1. 기동 시점의 argv 와 환경변수 → `seen.json` (${VAR} 확장 여부의 근거)
  2. 도구 정의 1개를 실어 세션 기동 토큰의 증분을 만든다

실제 서버가 아니다 — 도구를 부르면 고정 문자열을 돌려준다.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

TOOL = {
    "name": "probe_echo",
    "description": "측정용. 받은 문자열을 그대로 돌려준다.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "돌려받을 문자열"}},
        "required": ["text"],
    },
}


def main() -> None:
    out = Path(os.environ.get("PROBE_SEEN", "seen.json"))
    out.write_text(json.dumps({
        "argv": sys.argv[1:],
        # 우리가 mcp.json 에 적은 이름만 본다. 환경 전체를 남기면 비밀이 샌다.
        "env": {k: os.environ.get(k) for k in ("PROBE_HEADER", "PROBE_PLAIN")},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "id" not in msg:  # 알림에는 답하지 않는다
            continue
        method = msg.get("method")
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "jig-probe", "version": "0.0.1"},
            }
        elif method == "tools/list":
            result = {"tools": [TOOL]}
        elif method == "tools/call":
            result = {"content": [{"type": "text", "text": "probe-ok"}]}
        else:
            result = {}
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
