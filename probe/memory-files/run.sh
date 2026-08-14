#!/usr/bin/env bash
# 프로필 세션이 CLAUDE.md · AGENTS.md 를 실제로 싣는가?
#
# 컴파일러는 시스템 프롬프트를 PREAMBLE + BRIEF 로 조립해 --append-system-prompt-file
# 로 넘긴다. 그런데 사용자 전역(~/.claude/CLAUDE.md) · 프로젝트(./CLAUDE.md) ·
# AGENTS.md 는 컴파일러가 손대지 않는 CLI 자동 발견 경로다.
# --setting-sources user 가 그 발견까지 좁히는지는 문서로 알 수 없다 — 재야 안다.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SANDBOX="$ROOT/probe/sandbox/memory-files"

rm -rf "$SANDBOX"; mkdir -p "$SANDBOX"

cat > "$SANDBOX/CLAUDE.md" <<'MD'
# 프로젝트 지침

마커 코드는 PROJECT_MEM_4821 이다.
MD

cat > "$SANDBOX/AGENTS.md" <<'MD'
# 에이전트 지침

마커 코드는 AGENTS_MEM_9317 이다.
MD

ASK="아래 셋을 각각 한 줄로만 답해라. 컨텍스트에 없으면 그 줄에 '없음' 이라고 적어라.
1) 프로젝트 CLAUDE.md 의 마커 코드
2) AGENTS.md 의 마커 코드
3) 사용자 전역 메모리(~/.claude/CLAUDE.md)의 첫 H1 제목"

# 전역 적재 판정용 문자열. 샌드박스에 심을 수 없는 유일한 자리라(사용자의 실제 파일)
# **이 머신의 제목에서 따온다** — 다른 머신에서는 여기를 바꿔야 3열이 의미를 갖는다.
# 하드코딩된 채로 두면 남의 머신에서 전부 '없음' 으로 찍히고 회귀로 오독된다.
GLOBAL_MARK="${GLOBAL_MARK:-$(sed -n 's/^# *//p' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md" 2>/dev/null | head -1)}"
if [ -z "$GLOBAL_MARK" ]; then
  echo "전역 CLAUDE.md 의 첫 H1 을 못 읽었다 — GLOBAL_MARK=<문자열> 로 지정해라." >&2
  exit 1
fi
echo "전역 판정 문자열: $GLOBAL_MARK"
echo

run() {  # run <라벨> <출력파일> <argv...>
  local label="$1" out="$2"; shift 2
  echo "=== $label ==="
  ( cd "$SANDBOX" && "$@" --permission-mode acceptEdits -p "$ASK" ) \
    < /dev/null > "$out" 2>&1 || true
  sed 's/^/  /' "$out" | head -20
  echo
}

run "A. 맨 claude — 인자 없음 (기준선)" "$SANDBOX/out-plain.txt" \
  claude

run "B. 맨 claude + --setting-sources user" "$SANDBOX/out-user.txt" \
  claude --setting-sources user --mcp-config '{"mcpServers":{}}' --strict-mcp-config

# 프로필 세션이 실제로 뜨는 argv 그대로. project 는 샌드박스로 잡는다.
eval "ARGV=( $(cd "$ROOT" && HNS_PROJECT="$SANDBOX" ./bin/jig argv developer) )"
run "C. jig argv developer (프로필 세션)" "$SANDBOX/out-profile.txt" "${ARGV[@]}"

run "D. 맨 claude + --setting-sources user,project (귀속 확인)" "$SANDBOX/out-userproject.txt" \
  claude --setting-sources user,project --mcp-config '{"mcpServers":{}}' --strict-mcp-config

# AGENTS.md 가 CLAUDE.md 의 대체(fallback)인가? CLAUDE.md 를 치우고 다시 본다.
mv "$SANDBOX/CLAUDE.md" "$SANDBOX/CLAUDE.md.off"
run "E. CLAUDE.md 없이 맨 claude (AGENTS.md 대체 여부)" "$SANDBOX/out-noclaudemd.txt" claude
mv "$SANDBOX/CLAUDE.md.off" "$SANDBOX/CLAUDE.md"

# CLI 의 발견 범위는 `CLAUDE.md` 한 장이 아니다. 컴파일 시점 편입이 그 범위를 덮어야
# 하므로, 무엇까지 실리는지 재 둔다.
printf '# 프로젝트 규칙\n\n마커 PROJECT_MEM_4821.\n\n@imported.md\n' > "$SANDBOX/CLAUDE.md"
printf '가져온 파일의 마커는 IMPORTED_MEM_2244 이다.\n' > "$SANDBOX/imported.md"
printf '로컬 전용 마커는 LOCAL_MEM_6688 이다.\n' > "$SANDBOX/CLAUDE.local.md"
echo "=== F. 맨 claude — @import · CLAUDE.local.md 까지 싣는가 ==="
( cd "$SANDBOX" && claude --permission-mode acceptEdits -p \
  "아래 셋을 각각 한 줄로만. 컨텍스트에 없으면 '없음'. 파일은 읽지 말고 컨텍스트만 보고 답해라.
1) CLAUDE.md 의 마커
2) 그 안에서 @ 로 가져온 파일의 마커
3) CLAUDE.local.md 의 마커" ) < /dev/null > "$SANDBOX/out-scope.txt" 2>&1 || true
sed 's/^/  /' "$SANDBOX/out-scope.txt" | head -10
echo
for m in IMPORTED_MEM_2244 LOCAL_MEM_6688; do
  grep -q "$m" "$SANDBOX/out-scope.txt" \
    && echo "  $m 실림 — 편입이 이 범위를 덮어야 한다" \
    || echo "  $m 안 실림"
done
echo

echo "--- 판정 ---"
for f in out-plain out-user out-profile out-userproject out-noclaudemd; do
  printf '%-14s' "${f#out-}"
  for m in PROJECT_MEM_4821 AGENTS_MEM_9317 "$GLOBAL_MARK"; do
    if grep -q "$m" "$SANDBOX/$f.txt"; then printf ' %s=실림' "$m"; else printf ' %s=없음' "$m"; fi
  done
  echo
done
