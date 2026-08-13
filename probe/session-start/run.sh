#!/usr/bin/env bash
# SessionStart 훅의 stdout 이 실제로 에이전트 컨텍스트에 주입되는가?
#
# pending 등록부 표면화(bin/jig-pending-note)가 통째로 이 가정 위에 선다.
# 문서는 "stdout 이 컨텍스트에 추가된다" 고 하지만 [D], -p 경로에서도 그런지,
# matcher "startup" 이 -p 를 잡는지는 재 봐야 안다.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SANDBOX="$ROOT/probe/sandbox/session-start"

rm -rf "$SANDBOX"; mkdir -p "$SANDBOX"

cat > "$SANDBOX/note.sh" <<'SH'
#!/usr/bin/env bash
echo "PROBE_SESSION_NOTE_7734: 이 문장이 세션 컨텍스트에 주입되었는지 본다."
exit 0
SH
chmod +x "$SANDBOX/note.sh"

cat > "$SANDBOX/settings.json" <<JSON
{"disableBundledSkills": true,
 "hooks": {"SessionStart": [{"matcher": "startup", "hooks": [
   {"type": "command", "command": "$SANDBOX/note.sh", "timeout": 5}]}]}}
JSON

echo "=== SessionStart(startup) stdout 이 -p 세션의 컨텍스트에 오는가 ==="
claude --settings "$SANDBOX/settings.json" --setting-sources user \
  --mcp-config '{"mcpServers":{}}' --strict-mcp-config \
  --permission-mode acceptEdits \
  -p "세션 시작 때 주입된 노트가 있으면 마커 코드를 그대로 인용해라. 없으면 '노트 없음'이라고 답해라." \
  < /dev/null > "$SANDBOX/out.txt" 2>&1 || true

echo "--- 모델 출력 ---"
sed 's/^/  /' "$SANDBOX/out.txt" | head -10
echo
grep -q 'PROBE_SESSION_NOTE_7734' "$SANDBOX/out.txt" \
  && echo "주입됨 ✓ — 표면화 설계 성립" \
  || echo "주입 안 됨 — matcher 없이 재시도하거나 다른 이벤트를 봐야 한다"
