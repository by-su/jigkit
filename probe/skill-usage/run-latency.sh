#!/usr/bin/env bash
# 훅이 느리면 세션이 그만큼 느려지는가? 그리고 그 위험을 묶을 수 있는가?
#
# 실질 질문은 "얼마나 느려지나" 가 아니라 "상한을 걸 수 있나" 다.
# 세 구성을 같은 프롬프트로 돌려 벽시계 시간을 비교한다.
#   A) 즉시 끝나는 훅            — 기준선
#   B) sleep 8                   — 동기적으로 막는가?
#   C) sleep 8 + timeout: 2      — 상한이 먹히는가?
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SANDBOX="$ROOT/probe/sandbox/hook-latency"

rm -rf "$SANDBOX"; mkdir -p "$SANDBOX"

mk_hook() {  # $1=이름  $2=sleep 초
  local f="$SANDBOX/hook-$1.sh"
  printf '#!/usr/bin/env bash\ncat > /dev/null\nsleep %s\nexit 0\n' "$2" > "$f"
  chmod +x "$f"
  echo "$f"
}

run() {  # $1=라벨  $2=settings 경로
  local start end
  start=$(date +%s)
  claude --plugin-dir "$HERE/plugin" \
    --settings "$2" \
    --setting-sources user \
    --mcp-config '{"mcpServers":{}}' --strict-mcp-config \
    --permission-mode acceptEdits \
    -p "Run the echo probe using the probe-echo skill." \
    < /dev/null > "$SANDBOX/out-$1.txt" 2>&1 || true
  end=$(date +%s)
  local ok="스킬 미실행"
  grep -q 'PROBE_SKILL_INVOKED_9182' "$SANDBOX/out-$1.txt" && ok="스킬 실행됨"
  printf '  %-24s %3d초   %s\n' "$1" "$((end - start))" "$ok"
}

settings() {  # $1=이름  $2=hook 경로  $3=timeout(선택)
  local t=""
  [ -n "${3:-}" ] && t=", \"timeout\": $3"
  cat > "$SANDBOX/settings-$1.json" <<JSON
{
  "disableBundledSkills": true,
  "hooks": {
    "PreToolUse": [
      {"matcher": "Skill", "hooks": [{"type": "command", "command": "$2"$t}]}
    ]
  }
}
JSON
  echo "$SANDBOX/settings-$1.json"
}

echo "훅 지연 실측 (같은 프롬프트, 벽시계)"
echo
run "A-즉시"          "$(settings A "$(mk_hook A 0)")"
run "B-sleep8"        "$(settings B "$(mk_hook B 8)")"
run "C-sleep8-timeout2" "$(settings C "$(mk_hook C 8)" 2)"
echo
echo "B-A 가 8 에 가까우면 훅은 동기적으로 막는다."
echo "C 가 B 보다 확실히 짧으면 timeout 으로 상한을 걸 수 있다."
