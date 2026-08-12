#!/usr/bin/env bash
# 훅이 실패하면 스킬 호출이 막히는가?
#
# jigkit 의 기록 훅은 항상 exit 0 이지만, 스크립트가 깨지거나 사라지면 0 이 아닌 값이
# 나온다. 그때 세션이 멈춘다면 "통계 때문에 작업이 막히는" 최악의 실패 모드가 된다.
# exit 1 과 exit 2 를 각각 걸고 스킬이 실행되는지 대조한다.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SANDBOX="$ROOT/probe/sandbox/hook-failure"

rm -rf "$SANDBOX"; mkdir -p "$SANDBOX"

for rc in 1 2; do
  hook="$SANDBOX/hook-$rc.sh"
  cat > "$hook" <<SH
#!/usr/bin/env bash
cat > /dev/null
echo "probe: 훅이 의도적으로 실패한다 (exit $rc)" >&2
exit $rc
SH
  chmod +x "$hook"

  cat > "$SANDBOX/settings-$rc.json" <<JSON
{
  "disableBundledSkills": true,
  "hooks": {
    "PreToolUse": [
      {"matcher": "Skill", "hooks": [{"type": "command", "command": "$hook"}]}
    ]
  }
}
JSON

  echo "=== 훅 exit $rc ==="
  claude --plugin-dir "$HERE/plugin" \
    --settings "$SANDBOX/settings-$rc.json" \
    --setting-sources user \
    --mcp-config '{"mcpServers":{}}' --strict-mcp-config \
    --permission-mode acceptEdits \
    -p "Run the echo probe using the probe-echo skill." \
    < /dev/null > "$SANDBOX/out-$rc.txt" 2>&1 || echo "  (claude rc=$?)"

  if grep -q 'PROBE_SKILL_INVOKED_9182' "$SANDBOX/out-$rc.txt"; then
    echo "  스킬 실행됨 — 훅 실패가 막지 않는다"
  else
    echo "  스킬 실행 안 됨 — 훅 실패가 호출을 막는다"
  fi
  echo "  --- 모델이 본 것 ---"
  sed 's/^/  /' "$SANDBOX/out-$rc.txt" | head -12
  echo
done
