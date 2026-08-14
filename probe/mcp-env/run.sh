#!/usr/bin/env bash
# 두 가지를 잰다. 둘 다 카탈로그가 MCP 를 싣는 방식이 성립하는지의 근거다.
#
#   1. `--mcp-config` 파일 안의 `${VAR}` 를 Claude Code 가 확장하는가?
#      카탈로그(library/stacks/)는 커밋되므로 토큰을 값으로 넣을 수 없다.
#      확장이 안 되면 posthog 같은 항목은 env 를 못 싣고, 쓰려는 사람이
#      `library/mcp/<id>.json` 을 손으로 둬야 한다.
#   2. MCP 서버 1개가 세션 기동 토큰을 얼마나 늘리는가?
#      프로필에 무엇을 켤지의 판단 근거. (probe/PENDING.md 에 열려 있던 항목)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SANDBOX="$ROOT/probe/sandbox/mcp-env"

rm -rf "$SANDBOX"; mkdir -p "$SANDBOX"

# 확장 여부를 가릴 마커. 이 문자열이 서버에 도착하면 확장된 것이다.
export JIG_PROBE_SECRET="probe-secret-7734"
export PROBE_SEEN="$SANDBOX/seen.json"

cat > "$SANDBOX/none.json" <<'JSON'
{"mcpServers": {}}
JSON

cat > "$SANDBOX/one.json" <<JSON
{"mcpServers": {"jig-probe": {
  "command": "python3",
  "args": ["$HERE/server.py", "--tok=\${JIG_PROBE_SECRET}"],
  "env": {
    "PROBE_HEADER": "Bearer \${JIG_PROBE_SECRET}",
    "PROBE_PLAIN": "literal-value",
    "PROBE_SEEN": "$PROBE_SEEN"
  }}}}
JSON

# 기동 토큰만 보므로 프로필 빌드를 끌어오지 않는다 — 번들 스킬도 끈다.
cat > "$SANDBOX/settings.json" <<'JSON'
{"disableBundledSkills": true}
JSON

cat > "$SANDBOX/real.json" <<'JSON'
{"mcpServers": {"playwright": {"command": "npx", "args": ["-y", "@playwright/mcp@latest"]}}}
JSON

# 기준선과 대조군이 같은 디렉터리에서 돌아야 한다 — cwd 가 바뀌면 프로젝트 지침
# 편입분이 달라져 증분이 그 차이에 묻힌다 [M].
run_once() {  # <mcp-config> -> 기동 토큰 합
  ( cd "$SANDBOX" && claude --settings "$SANDBOX/settings.json" --setting-sources user \
    --mcp-config "$1" --strict-mcp-config \
    --output-format json -p "hi" < /dev/null 2> "$SANDBOX/err.txt" ) \
  | python3 -c 'import json,sys; u=json.load(sys.stdin).get("usage",{}); print(sum(u.get(k) or 0 for k in ("input_tokens","cache_read_input_tokens","cache_creation_input_tokens")))'
}

measure() {  # 캐시 상태에 흔들리므로 최솟값을 쓴다 (cli.measure 와 같은 규칙)
  local best="" v
  for _ in 1 2; do
    v="$(run_once "$1")"
    if [ -z "$best" ] || [ "$v" -lt "$best" ]; then
      best="$v"
    fi
  done
  echo "$best"
}

echo "=== 1) MCP 서버 0개 (기준선) ==="
BASE="$(measure "$SANDBOX/none.json")"
echo "  $BASE 토큰"

echo
echo "=== 2) MCP 서버 1개 (도구 1개) ==="
ONE="$(measure "$SANDBOX/one.json")"
echo "  $ONE 토큰   증분 $((ONE - BASE))"

echo
echo "=== 3) 실제 서버 1개 (@playwright/mcp, 도구 24개) ==="
REAL="$(measure "$SANDBOX/real.json")"
echo "  $REAL 토큰   증분 $((REAL - BASE))"

echo
echo "=== 4) \${VAR} 가 확장돼 서버에 도착했는가 ==="
if [ -f "$PROBE_SEEN" ]; then
  sed 's/^/  /' "$PROBE_SEEN"
  echo
  if grep -q "$JIG_PROBE_SECRET" "$PROBE_SEEN"; then
    echo "  확장됨 ✓ — 카탈로그에 \${VAR} 참조를 실어도 된다"
  else
    echo "  확장 안 됨 ✗ — 토큰이 필요한 항목은 library/mcp/<id>.json 을 손으로 둬야 한다"
  fi
else
  echo "  서버가 기동되지 않았다 ($PROBE_SEEN 없음). stderr:"
  sed 's/^/  /' "$SANDBOX/err.txt" | head -20
fi

echo
echo "=== 5) 변수가 설정돼 있지 않으면 어떻게 되는가 ==="
# 실제로 켜는 사람이 겪을 경로다. 조용히 통과하면 원격 서버가 401 을 주고,
# 설정 실수가 인증 문제로 보인다.
rm -f "$PROBE_SEEN"
sed 's/JIG_PROBE_SECRET/JIG_PROBE_UNSET_XYZ/g' "$SANDBOX/one.json" > "$SANDBOX/unset.json"
UNSET_RC=0
( cd "$SANDBOX" && claude --settings "$SANDBOX/settings.json" --setting-sources user \
  --mcp-config "$SANDBOX/unset.json" --strict-mcp-config \
  --output-format json -p "hi" < /dev/null ) > /dev/null 2> "$SANDBOX/err-unset.txt" || UNSET_RC=$?
echo "  claude 종료코드: $UNSET_RC"
if [ -f "$PROBE_SEEN" ]; then
  sed 's/^/  /' "$PROBE_SEEN"
  echo
  grep -q '\${JIG_PROBE_UNSET_XYZ}' "$PROBE_SEEN" \
    && echo "  치환 없이 리터럴이 그대로 간다 — 조용한 실패다" \
    || echo "  빈 문자열로 치환됐다"
else
  echo "  서버가 기동되지 않았다 — 미설정이 기동을 막는다"
fi
