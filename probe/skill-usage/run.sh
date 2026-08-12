#!/usr/bin/env bash
# M0 — 훅이 스킬 호출에 발화하는가?
#
# matcher 를 "*" 로 두고 전부 잡아서, 스킬을 부를 때 어떤 tool_name 이 오는지
# 그리고 stdin JSON 에서 **어떤 스킬인지** 식별 가능한지를 본다.
# 이 두 가지가 jig usage 설계의 전제다.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SANDBOX="$ROOT/probe/sandbox/skill-usage"

rm -rf "$SANDBOX"
mkdir -p "$SANDBOX"
LOG="$SANDBOX/hook.log"

cat > "$SANDBOX/settings.json" <<JSON
{
  "disableBundledSkills": true,
  "hooks": {
    "PreToolUse": [
      {"matcher": "*", "hooks": [{"type": "command", "command": "$HERE/hook.sh $LOG PreToolUse"}]}
    ],
    "PostToolUse": [
      {"matcher": "*", "hooks": [{"type": "command", "command": "$HERE/hook.sh $LOG PostToolUse"}]}
    ]
  }
}
JSON

echo "== 실행 =="
claude \
  --plugin-dir "$HERE/plugin" \
  --settings "$SANDBOX/settings.json" \
  --setting-sources user \
  --mcp-config '{"mcpServers":{}}' --strict-mcp-config \
  --permission-mode acceptEdits \
  -p "Run the echo probe using the probe-echo skill." \
  > "$SANDBOX/stdout.txt" 2>"$SANDBOX/stderr.txt" || echo "rc=$?"

echo "== 모델 출력 =="
cat "$SANDBOX/stdout.txt"

echo
echo "== 스킬이 실제로 불렸는가 =="
grep -q 'PROBE_SKILL_INVOKED_9182' "$SANDBOX/stdout.txt" \
  && echo "yes — 마커가 출력됨" || echo "no — 마커 없음 (스킬 미호출 가능성)"

echo
echo "== 훅 로그 =="
if [ -s "$LOG" ]; then
  cat "$LOG"
else
  echo "(비어 있음 — 훅이 발화하지 않았다)"
fi
