#!/usr/bin/env bash
# 커밋 게이트가 성립하는가?
#
# 두 가정에 M1 전체가 걸려 있다.
#   1) PreToolUse 가 tool_name "Bash" 로도 발화하고 tool_input.command 에 명령이 오는가
#   2) exit 2 로 막을 때 stderr 가 **모델에게** 전달되는가
#      (Skill 에서는 확인했다 — probe/results/skill-usage.md. Bash 에서도 같은지)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
SANDBOX="$ROOT/sandbox/commit-gate"

rm -rf "$SANDBOX"; mkdir -p "$SANDBOX"
LOG="$SANDBOX/payload.log"

# 1) 페이로드를 적기만 하는 훅 — 발화 여부와 모양을 본다
cat > "$SANDBOX/observe.sh" <<SH
#!/usr/bin/env bash
cat >> "$LOG"
printf '\n' >> "$LOG"
exit 0
SH

# 2) 특정 명령만 골라 exit 2 로 막는 훅 — 차단과 stderr 전달을 본다
cat > "$SANDBOX/block.sh" <<'SH'
#!/usr/bin/env bash
payload=$(cat)
case "$payload" in
  *PROBE_BLOCK_ME*)
    echo "PROBE_STDERR_MARKER_4417: 이 명령은 게이트가 막았다." >&2
    exit 2 ;;
esac
exit 0
SH
chmod +x "$SANDBOX/observe.sh" "$SANDBOX/block.sh"

settings() {
  cat > "$SANDBOX/settings-$1.json" <<JSON
{"disableBundledSkills": true,
 "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
   {"type": "command", "command": "$2", "timeout": 5}]}]}}
JSON
  echo "$SANDBOX/settings-$1.json"
}

run() {  # $1=settings  $2=프롬프트
  claude --settings "$1" --setting-sources user \
    --mcp-config '{"mcpServers":{}}' --strict-mcp-config \
    --permission-mode acceptEdits -p "$2" < /dev/null 2>&1 || true
}

echo "=== 1. Bash 훅이 발화하는가 / 페이로드 모양 ==="
run "$(settings observe "$SANDBOX/observe.sh")" \
    "Run exactly this shell command and nothing else: echo PROBE_HELLO_2231" > "$SANDBOX/out1.txt"
if [ -s "$LOG" ]; then
  echo "발화함. 첫 페이로드:"
  head -c 600 "$LOG"; echo
else
  echo "발화하지 않았다 — M1 의 강제 방식을 다시 잡아야 한다"
fi

echo
echo "=== 2. exit 2 가 막고, stderr 가 모델에게 가는가 ==="
run "$(settings block "$SANDBOX/block.sh")" \
    "Run exactly this shell command: echo PROBE_BLOCK_ME. If it is blocked, quote the blocker message verbatim." \
    > "$SANDBOX/out2.txt"
echo "--- 모델 출력 ---"
sed 's/^/  /' "$SANDBOX/out2.txt" | head -20
echo
grep -q 'PROBE_STDERR_MARKER_4417' "$SANDBOX/out2.txt" \
  && echo "stderr 가 모델에게 전달됨 ✓" \
  || echo "stderr 가 모델 출력에 없음 — 메시지 전달 경로를 다시 봐야 한다"
