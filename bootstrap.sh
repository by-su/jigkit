#!/usr/bin/env bash
# jigkit 설치 부트스트랩 — 새 클론을 검증된 동작 상태로 만든다.
#
# bash 인 이유: 프리플라이트가 검사 대상에 의존하면 안 된다. `jig setup` 서브커맨드로
# 만들면 cli.py -> build.py -> `import yaml` 이라, PyYAML 이 없을 때
# "PyYAML 이 없다"고 말해줄 기회조차 없이 트레이스백으로 죽는다.
#
# 소스 **등록**은 하지 않는다. library/sources.yaml 이 커밋되므로 새 클론은 등록을 이미
# 갖고 있다. 여기서 URL 을 또 적으면 진실이 두 곳이 된다. 하는 일은 캐시 하이드레이션이다.
set -euo pipefail

# 어디에 클론했든 맞도록 자기 위치에서 유도한다. 경로 하드코딩이 애초 문제였다.
# 셸 빌트인만 쓴다 — 이 줄은 프리플라이트보다 먼저 돌기 때문에 PATH 가 망가져 있어도
# 맞아야 한다. `dirname` 을 쓰면 그게 없을 때 빈 문자열이 되고, `cd ""` 는 성공해서
# 엉뚱한 디렉터리를 ROOT 로 잡는다 — 조용히 틀리는 실패다.
_self="${BASH_SOURCE[0]}"
case "$_self" in
  */*) _dir="${_self%/*}" ;;
  *)   _dir="." ;;
esac
ROOT="$(cd "$_dir" && pwd)"
JIG="$ROOT/bin/jig"

DO_SYNC=1
DO_PATH=0
LANG_SET=""

usage() {
  cat <<'USAGE'
사용법: ./bootstrap.sh [옵션]

  (없음)      프리플라이트 -> 전역 지침 -> jig sync -> jig doctor -> PATH 안내
  --no-sync   네트워크를 타지 않는다 (프리플라이트 + doctor 만)
  --path      셸 rc 에 PATH export 를 추가한다 (멱등)
  --lang L    전역 지침의 응답 언어를 L 로 (기본: 지금 값 유지). 나중에는 jig lang
  -h, --help  이 도움말

여러 번 실행해도 안전하다.
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --no-sync) DO_SYNC=0 ;;
    --path)    DO_PATH=1 ;;
    --lang)    shift; [ $# -gt 0 ] || { echo "--lang 에 언어가 필요하다 (예: --lang English)" >&2; exit 1; }; LANG_SET="$1" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "모르는 옵션: $1" >&2; usage >&2; exit 1 ;;
  esac
  shift
done

ok()   { printf '  ok    %-11s %s\n' "$1" "${2:-}"; }
fail() { printf '  FAIL  %-11s %s\n' "$1" "${2:-}" >&2; }

echo
echo "jigkit bootstrap  ($ROOT)"
echo

# ---------------------------------------------------------------- 프리플라이트
missing=0

if command -v python3 >/dev/null 2>&1; then
  ok python3 "$(python3 --version 2>&1 | awk '{print $2}')"
else
  fail python3 "없다. macOS: brew install python3"
  missing=1
fi

if [ "$missing" -eq 0 ] && python3 -c 'import yaml' >/dev/null 2>&1; then
  ok PyYAML "$(python3 -c 'import yaml; print(yaml.__version__)' 2>/dev/null)"
elif [ "$missing" -eq 0 ]; then
  fail PyYAML "없다. python3 -m pip install --user PyYAML"
  missing=1
fi

if command -v git >/dev/null 2>&1; then
  ok git "$(git --version 2>&1 | awk '{print $3}')"
else
  fail git "없다. 스킬 소스를 받으려면 필요하다."
  missing=1
fi

# claude 는 셸 함수로 감싸져 있을 수 있어 command -v 로는 안 잡힐 수 있다.
if command -v claude >/dev/null 2>&1 || [ -x "$HOME/.claude/local/claude" ]; then
  ok claude "found"
else
  fail claude "없다. https://claude.com/claude-code 에서 설치한다."
  missing=1
fi

if [ "$missing" -ne 0 ]; then
  echo
  echo "  위 항목을 채우고 다시 실행한다." >&2
  exit 1
fi

# ---------------------------------------------------------------- 전역 지침
# `~/.claude/CLAUDE.md` 는 모든 세션에 실린다 — 프로필 세션도 그렇다는 것을 쟀다
# (probe/results/memory-files.md). 기본 지침을 여기에 깔아 새 머신이 빈손으로
# 시작하지 않게 한다.
#
# **덮어쓴다.** 이 스크립트는 "다 밀고 처음부터" 를 전제로 하고, 그래야 여러 번 돌려도
# 같은 상태가 된다. 손으로 고친 내용이 있으면 여기서 사라진다 —
# reset-and-setup.sh 로 왔다면 그 전에 tar 백업이 남는다.
#
# 설치는 `jig lang` 한 곳에서만 한다. 여기서 따로 `cp` 하면 규칙이 두 벌이 되고,
# 언젠가 한쪽만 고쳐진다. 인자 없이 부르면 언어를 그대로 두고 설치만 한다.
if [ -n "$LANG_SET" ]; then set -- "$LANG_SET"; else set -- --install; fi
if ! global_out="$("$JIG" lang "$@" 2>&1)"; then
  fail global "전역 지침을 깔지 못했다"
  echo "$global_out" >&2
  exit 1
fi
# **결과를 확인한다.** 종료 코드만 보면, 설치 대신 현재 언어만 출력하고 끝나는 경로가
# `ok` 로 찍힌다 — 실제로 그렇게 한 번 났다. 안 깔린 것이 성공으로 보이는 게 최악이다.
global_line="$(echo "$global_out" | grep '^installed ' | tail -1 || true)"
if [ -z "$global_line" ]; then
  fail global "설치 결과를 확인하지 못했다"
  echo "$global_out" >&2
  exit 1
fi
ok global "${global_line#installed }"
# `[ ... ] && ok ...` 로 쓰면 안 된다 — 조건이 거짓일 때 목록 전체가 1 로 끝나고
# `set -e` 가 여기서 부트스트랩을 죽인다.
if [ -n "$LANG_SET" ]; then ok language "$LANG_SET"; fi

# ---------------------------------------------------------------- 캐시
if [ "$DO_SYNC" -eq 1 ]; then
  if ! sync_out="$("$JIG" sync 2>&1)"; then
    fail sync "실패"
    echo "$sync_out" >&2
    exit 1
  fi
  if [ -z "$sync_out" ]; then
    ok sync "등록된 소스 없음 — jig source add <url>"
  else
    ok sync "$(echo "$sync_out" | awk '{printf "%s %s · ", $2, $3}' | sed 's/ · $//')"
  fi
else
  printf '  skip  %-11s %s\n' "sync" "--no-sync"
fi

# ---------------------------------------------------------------- 동작 확인
if doctor_out="$("$JIG" doctor 2>&1)"; then
  ok doctor "프로필 $(echo "$doctor_out" | grep -c '^ok ')개 통과"
else
  fail doctor "검사 실패"
  echo "$doctor_out" >&2
  exit 1
fi

# ---------------------------------------------------------------- PATH
export_line="export PATH=\"$ROOT/bin:\$PATH\""

if command -v jig >/dev/null 2>&1 && [ "$(command -v jig)" = "$JIG" ]; then
  ok PATH "jig -> $JIG"
  echo
  echo "  준비됐다.  jig list"
  echo
  exit 0
fi

if [ "$DO_PATH" -eq 1 ]; then
  case "${SHELL##*/}" in
    zsh)  rc="$HOME/.zshrc" ;;
    bash) rc="$HOME/.bashrc" ;;
    *)    rc="" ;;
  esac

  if [ -n "$rc" ]; then
    if [ -f "$rc" ] && grep -qF "$ROOT/bin" "$rc"; then
      ok PATH "이미 $rc 에 있다"
    else
      printf '\n# jigkit\n%s\n' "$export_line" >> "$rc"
      ok PATH "$rc 에 추가했다"
    fi
    echo
    echo "  새 셸을 열거나:  source $rc"
    echo
    exit 0
  fi
  echo
  echo "  ${SHELL##*/} 은 자동 추가를 지원하지 않는다. 아래를 직접 넣는다."
fi

echo
echo "  PATH 에 jig 가 없다. 아래 한 줄을 셸 설정에 넣는다:"
echo
echo "    $export_line"
echo
echo "  또는:  ./bootstrap.sh --path"
echo "  지금 바로 쓰려면:  $JIG list"
echo
