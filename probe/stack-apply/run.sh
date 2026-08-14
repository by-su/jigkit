#!/usr/bin/env bash
# 스택 훅이 **한 번만** 도는가? 그리고 다른 스택의 훅이 같이 뜨지 않는가?
#
# 단위 검사는 "settings.json 에 항목이 1개다" 까지만 본다. 그건 배치의 모양이고,
# 실제로 몇 번 도는지는 Claude 가 정한다 — matcher 는 도구 이름만 거르고 경로는 모르며
# 매칭되는 훅은 전부 병렬로 돈다 [D]. 그 문장이 우리 배치에서 어떻게 나타나는지 여기서 잰다.
#
# 파이썬·타입스크립트 스택을 한 프로젝트에 겹쳐 넣고 `.py` 하나를 고친 뒤,
# 디스패처가 남긴 마커를 센다. 기대: py 분기 1줄, ts 분기 0줄.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SANDBOX="$ROOT/probe/sandbox/stack-apply"
LOG="$SANDBOX/fired.log"

rm -rf "$SANDBOX"; mkdir -p "$SANDBOX"
cd "$SANDBOX"

# 실제 도구를 깔지 않는다 — 재려는 것은 "몇 번 불렸나" 이고, 도구 설치는 그 답을 바꾸지 않는다.
printf '[project]\nname = "probe"\ndependencies = []\n\n[dependency-groups]\ndev = []\n' > pyproject.toml
printf '{"name":"probe","devDependencies":{}}\n' > package.json

# apply 는 저장소 안에 아무것도 만들지 않는다 — MCP 정의는 카탈로그에 한 벌만 산다.
# 예전에는 library/mcp/ 에 사본을 깔아서 프로브가 그것을 되돌려야 했다.
"$ROOT/bin/jig" stack apply python "$SANDBOX" --apply > /dev/null
"$ROOT/bin/jig" stack apply typescript "$SANDBOX" --apply > /dev/null

echo "=== 배치 결과: 이벤트당 훅 항목 수 ==="
python3 - <<'PY'
import json
s = json.load(open(".claude/settings.json"))
for event, entries in (s.get("hooks") or {}).items():
    print(f"  {event}: 항목 {len(entries)}개")
PY

# 디스패처의 실행 명령을 마커 기록으로 갈아 끼운다 — 무엇이 불렸는지만 남기면 된다.
python3 - <<'PY'
import re
for path in (".claude/hooks/jig-format",):
    text = open(path).read()
    text = re.sub(r"'[^']*ruff[^']*'", "'echo FIRED-py >> " + "fired.log'", text)
    text = re.sub(r"'[^']*biome[^']*'", "'echo FIRED-ts >> " + "fired.log'", text)
    open(path, "w").write(text)
PY

: > "$LOG"
echo
echo "=== .py 하나를 고친다 (Edit 1회) ==="
cat > "$SANDBOX/settings-probe.json" <<JSON
{"disableBundledSkills": true,
 "hooks": {"PostToolUse": [{"matcher": "Edit|Write", "hooks": [
   {"type": "command", "command": "$SANDBOX/.claude/hooks/jig-format", "timeout": 20}]}]}}
JSON

claude --settings "$SANDBOX/settings-probe.json" --setting-sources user \
  --mcp-config '{"mcpServers":{}}' --strict-mcp-config \
  --permission-mode acceptEdits \
  --add-dir "$SANDBOX" \
  -p "$SANDBOX/app.py 라는 파일을 만들고 안에 'x = 1' 한 줄만 써라. 다른 파일은 건드리지 마라." \
  < /dev/null > "$SANDBOX/out.txt" 2>&1 || true

echo "--- 디스패처가 남긴 기록 ---"
if [ -s "$LOG" ]; then sed 's/^/  /' "$LOG"; else echo "  (없음)"; fi
py=$(grep -c 'FIRED-py' "$LOG" 2>/dev/null || true)
ts=$(grep -c 'FIRED-ts' "$LOG" 2>/dev/null || true)
echo
echo "py 분기 ${py:-0}회 · ts 분기 ${ts:-0}회   (기대: 1 / 0)"
[ "${py:-0}" = "1" ] && [ "${ts:-0}" = "0" ] \
  && echo "성립 ✓ — 스택을 겹쳐도 확장자에 맞는 것만 한 번 돈다" \
  || echo "어긋남 — 결과를 probe/results/stack-hooks.md 에 적고 배치 모양을 다시 본다"

# ---------------------------------------------------------------------------
# 같은 settings **파일 안**의 동일 command 항목 2개는 dedupe 되는가?
#
# 문서는 "여러 settings 파일에 같은 handler 를 정의하면 한 번만 돈다" 고만 말한다 [D].
# 한 파일 안의 중복은 안 적혀 있다. 이 답이 배치 전략을 정한다 — dedupe 되지 않으면
# command 문자열로 항목을 찾아 교체하는 현재 방식이 유일한 안전한 길이다.
echo
echo "=== 한 파일 안의 동일 command 항목 2개 ==="
cat > "$SANDBOX/settings-dup.json" <<JSON
{"disableBundledSkills": true,
 "hooks": {"PostToolUse": [
   {"matcher": "Edit|Write", "hooks": [
     {"type": "command", "command": "$SANDBOX/.claude/hooks/jig-format", "timeout": 20}]},
   {"matcher": "Edit|Write", "hooks": [
     {"type": "command", "command": "$SANDBOX/.claude/hooks/jig-format", "timeout": 20}]}]}}
JSON

: > "$LOG"
claude --settings "$SANDBOX/settings-dup.json" --setting-sources user \
  --mcp-config '{"mcpServers":{}}' --strict-mcp-config \
  --permission-mode acceptEdits --add-dir "$SANDBOX" \
  -p "$SANDBOX/dup.py 라는 파일을 만들고 안에 'y = 2' 한 줄만 써라." \
  < /dev/null > "$SANDBOX/out-dup.txt" 2>&1 || true

dup=$(grep -c 'FIRED-py' "$LOG" 2>/dev/null || true)
echo "py 분기 ${dup:-0}회"
case "${dup:-0}" in
  1) echo "dedupe 됨 — 같은 파일 안의 중복도 한 번만 돈다" ;;
  0) echo "발화 안 됨 — 앞 절이 통과했는데 여기서 0이면 설정 형태를 다시 본다" ;;
  *) echo "dedupe 안 됨 (${dup}회) — 항목을 덧붙이면 그만큼 늘어난다. command 로 찾아 교체하는 방식이 필수다" ;;
esac
