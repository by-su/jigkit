#!/usr/bin/env bash
# Claude Code 완전 초기화 + jigkit 세팅 — "방금 설치한 것" 상태로 되돌린 뒤 jigkit 을 붙인다.
#
# 이 파일 하나만 다른 컴퓨터로 복사해도 동작한다. 옆에 jigkit 클론이 없으면 직접 clone 한다.
# 지우기 전에 항상 tar 백업을 만들고, --restore 로 되돌릴 수 있다.
#
# 지우지 않는 것:
#   - claude 실행 파일 (~/.claude/local, ~/.local/bin, npm 전역 — 설치본은 건드리지 않는다)
#   - 로그인 자격증명 (키체인 / ~/.claude/.credentials.json — 다시 로그인할 일은 없다)
#   - 셸 rc 의 PATH 줄
set -euo pipefail

# 자기 위치에서 유도한다. 셸 빌트인만 쓴다 — PATH 가 비어 있어도 맞아야 한다.
_self="${BASH_SOURCE[0]}"
case "$_self" in
  */*) _dir="${_self%/*}" ;;
  *)   _dir="." ;;
esac
SELF_DIR="$(cd "$_dir" && pwd)"

OS="$(uname -s)"
CLAUDE_DIR="$HOME/.claude"
BACKUP_DIR="$HOME/.claude-reset-backups"
REPO_URL="https://github.com/by-su/jigkit.git"
CLONE_TO="$HOME/jigkit"

DRY=0
ASSUME_YES=0
KEEP_HISTORY=0
DO_BOOTSTRAP=1
BOOTSTRAP_ARGS=()
FORCE=0
RESTORE=""

# 절대 지우지 않는다 — CLI 설치본이 여기 있을 수 있다.
KEEP_ALWAYS="local"
# --keep-history 를 주면 남긴다. projects/ 안에 memory/ 도 들어 있다.
HISTORY_ITEMS="projects history.jsonl sessions plans todos file-history shell-snapshots"

usage() {
  cat <<'USAGE'
사용법: ./reset-and-setup.sh [옵션]

  (없음)          백업 -> ~/.claude 초기화 -> jigkit 확보 -> bootstrap.sh
  --dry-run       무엇을 지울지만 보여주고 끝낸다
  -y, --yes       확인 프롬프트를 건너뛴다
  --keep-history  대화 기록·메모리는 남긴다 (projects/, history.jsonl, sessions/, plans/ ...)
  --no-bootstrap  초기화만 하고 jigkit 세팅은 하지 않는다
  --path          bootstrap 에 --path 를 넘긴다 (셸 rc 에 PATH 추가 — 새 컴퓨터면 권장)
  --clone-to DIR  jigkit 을 여기에 clone 한다 (기본 ~/jigkit, 옆에 클론이 있으면 그걸 쓴다)
  --repo URL      clone 할 저장소 (기본 by-su/jigkit)
  --restore FILE  백업 tar 로 되돌린다 (다른 작업은 하지 않는다)
  --force         Claude 가 떠 있어도 진행한다 (권하지 않는다)
  -h, --help      이 도움말

여러 번 실행해도 안전하다. 백업은 ~/.claude-reset-backups/ 에 쌓인다.
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)      DRY=1 ;;
    -y|--yes)       ASSUME_YES=1 ;;
    --keep-history) KEEP_HISTORY=1 ;;
    --no-bootstrap) DO_BOOTSTRAP=0 ;;
    --path)         BOOTSTRAP_ARGS+=(--path) ;;
    --no-sync)      BOOTSTRAP_ARGS+=(--no-sync) ;;
    --clone-to)     shift; [ $# -gt 0 ] || { echo "--clone-to 에 경로가 필요하다" >&2; exit 1; }; CLONE_TO="$1" ;;
    --repo)         shift; [ $# -gt 0 ] || { echo "--repo 에 URL 이 필요하다" >&2; exit 1; }; REPO_URL="$1" ;;
    --restore)      shift; [ $# -gt 0 ] || { echo "--restore 에 파일이 필요하다" >&2; exit 1; }; RESTORE="$1" ;;
    --force)        FORCE=1 ;;
    -h|--help)      usage; exit 0 ;;
    *) echo "모르는 옵션: $1" >&2; usage >&2; exit 1 ;;
  esac
  shift
done

ok()   { printf '  ok    %-11s %s\n' "$1" "${2:-}"; }
skip() { printf '  skip  %-11s %s\n' "$1" "${2:-}"; }
fail() { printf '  FAIL  %-11s %s\n' "$1" "${2:-}" >&2; }
warn() { printf '  warn  %-11s %s\n' "$1" "${2:-}"; }

confirm() { # $1 = 프롬프트. --yes 면 통과.
  [ "$ASSUME_YES" -eq 1 ] && return 0
  local ans=""
  printf '%s [y/N] ' "$1"
  if [ -r /dev/tty ]; then read -r ans < /dev/tty || true; else read -r ans || true; fi
  case "$ans" in y|Y|yes|YES) return 0 ;; *) echo "중단했다."; exit 1 ;; esac
}

# HOME 이 비어 있으면 rm 대상이 / 로 미끄러진다. 먼저 막는다.
if [ -z "${HOME:-}" ] || [ ! -d "$HOME" ]; then
  fail HOME "\$HOME 이 비었거나 디렉터리가 아니다. 중단한다."
  exit 1
fi

# ---------------------------------------------------------------- 백업 / 복원
make_backup() { # $1 = 라벨. 성공하면 BACKUP_FILE 을 채운다.
  local items=() f
  [ -d "$CLAUDE_DIR" ] && items+=(".claude")
  # jigkit 전역 사용 로그도 담는다 — 지우는 것은 되돌릴 수 있어야 한다.
  [ -e "$HOME/.jigkit/skill-usage.jsonl" ] && items+=(".jigkit/skill-usage.jsonl")
  for f in ".claude.json" ".claude.json.backup"; do
    [ -e "$HOME/$f" ] && items+=("$f")
  done
  if [ ${#items[@]} -eq 0 ]; then
    BACKUP_FILE=""
    skip backup "지울 것이 없다"
    return 0
  fi
  mkdir -p "$BACKUP_DIR"
  BACKUP_FILE="$BACKUP_DIR/claude-$1-$(date +%Y%m%d-%H%M%S).tgz"
  # 소켓·전송 중 파일에 tar 가 경고를 내고 1 로 끝날 수 있다. 알맹이가 읽히면 진행한다.
  local out
  if ! out="$(tar -czf "$BACKUP_FILE" -C "$HOME" "${items[@]}" 2>&1)"; then
    if tar -tzf "$BACKUP_FILE" >/dev/null 2>&1; then
      warn backup "tar 경고가 있었지만 아카이브는 읽힌다"
      [ -n "$out" ] && printf '%s\n' "$out" | sed 's/^/          /' >&2
    else
      fail backup "실패 — 아무것도 지우지 않았다"
      printf '%s\n' "$out" >&2
      exit 1
    fi
  fi
  ok backup "$BACKUP_FILE ($(wc -c < "$BACKUP_FILE" | tr -d ' ') bytes)"
}

if [ -n "$RESTORE" ]; then
  [ -f "$RESTORE" ] || { fail restore "$RESTORE 가 없다"; exit 1; }
  tar -tzf "$RESTORE" >/dev/null 2>&1 || { fail restore "$RESTORE 를 읽을 수 없다"; exit 1; }
  echo
  echo "복원:  $RESTORE  ->  $HOME"
  echo "지금 상태는 먼저 백업한다."
  echo
  confirm "진행할까?"
  make_backup "pre-restore"
  [ -d "$CLAUDE_DIR" ] && find "$CLAUDE_DIR" -mindepth 1 -maxdepth 1 ! -name "$KEEP_ALWAYS" -exec rm -rf {} +
  rm -f "$HOME/.claude.json" "$HOME/.claude.json.backup" "$HOME/.jigkit/skill-usage.jsonl"
  tar -xzf "$RESTORE" -C "$HOME"
  ok restore "되돌렸다"
  echo
  exit 0
fi

# ---------------------------------------------------------------- 프리플라이트
echo
echo "Claude Code 초기화 + jigkit 세팅   ($OS)"
echo

# 실행 중인 Claude 는 종료할 때 설정을 다시 써서 초기화를 조용히 되돌린다.
# --dry-run 은 아무것도 건드리지 않으니 세션 안에서도 볼 수 있게 둔다.
if [ -n "${CLAUDECODE:-}" ]; then
  if [ "$DRY" -eq 1 ] || [ "$FORCE" -eq 1 ]; then
    warn session "Claude Code 세션 안이다"
  else
    fail session "Claude Code 세션 안에서 돌리고 있다."
    echo "        일반 터미널에서, Claude 창을 모두 닫고 실행한다." >&2
    echo "        (정말 강행하려면 --force)" >&2
    exit 1
  fi
fi

running=""
for pat in 'Claude\.app/Contents/MacOS/Claude' 'share/claude/versions' '@anthropic-ai/claude-code' 'claude-code/cli\.js'; do
  for p in $(pgrep -f "$pat" 2>/dev/null || true); do
    [ "$p" = "$$" ] && continue
    [ "$p" = "${PPID:-0}" ] && continue
    running="$running $p"
  done
done
if [ -n "$running" ]; then
  if [ "$FORCE" -eq 1 ] || [ "$DRY" -eq 1 ]; then
    warn running "Claude 프로세스가 떠 있다 (PID$running) — --force 로 진행한다"
  else
    fail running "Claude 가 실행 중이다 (PID$running)"
    echo "        종료하면 설정을 다시 쓰기 때문에 초기화가 되돌아간다." >&2
    echo "        모두 닫고 다시 실행한다. (강행: --force)" >&2
    exit 1
  fi
fi

CLAUDE_BIN=""
if command -v claude >/dev/null 2>&1; then
  CLAUDE_BIN="$(command -v claude)"
  ok claude "$CLAUDE_BIN"
elif [ -x "$CLAUDE_DIR/local/claude" ]; then
  CLAUDE_BIN="$CLAUDE_DIR/local/claude"
  ok claude "$CLAUDE_BIN"
elif [ -x "$HOME/.local/bin/claude" ]; then
  CLAUDE_BIN="$HOME/.local/bin/claude"
  ok claude "$CLAUDE_BIN"
else
  warn claude "없다 — 초기화는 하지만 설치는 따로 해야 한다"
  echo "          npm i -g @anthropic-ai/claude-code   또는   https://claude.com/claude-code"
fi

# jigkit 세팅까지 갈 거라면 그 의존성이 있는지 여기서 확인한다.
# 다 지운 뒤에 "PyYAML 이 없다"를 알게 되는 건 최악의 순서다.
if [ "$DO_BOOTSTRAP" -eq 1 ]; then
  miss=0
  if command -v git >/dev/null 2>&1; then
    ok git "$(git --version 2>&1 | awk '{print $3}')"
  else
    fail git "없다. macOS: xcode-select --install / Debian: apt install git"
    miss=1
  fi
  if command -v python3 >/dev/null 2>&1; then
    ok python3 "$(python3 --version 2>&1 | awk '{print $2}')"
    if python3 -c 'import yaml' >/dev/null 2>&1; then
      ok PyYAML "$(python3 -c 'import yaml; print(yaml.__version__)' 2>/dev/null)"
    else
      fail PyYAML "없다. python3 -m pip install --user PyYAML"
      miss=1
    fi
  else
    fail python3 "없다. macOS: brew install python3 / Debian: apt install python3 python3-yaml"
    miss=1
  fi
  if [ "$miss" -ne 0 ]; then
    echo
    echo "  위를 채우고 다시 실행한다. 초기화만 하려면 --no-bootstrap." >&2
    exit 1
  fi
fi

# ---------------------------------------------------------------- 대상 수집
kept() { # $1 = ~/.claude 아래 항목 이름
  local n="$1" k
  for k in $KEEP_ALWAYS; do [ "$n" = "$k" ] && return 0; done
  # 로그인은 건드리지 않는다 — 이 스크립트는 설정을 초기화할 뿐 로그아웃시키지 않는다.
  if [ "$n" = ".credentials.json" ]; then return 0; fi
  if [ "$KEEP_HISTORY" -eq 1 ]; then
    for k in $HISTORY_ITEMS; do [ "$n" = "$k" ] && return 0; done
  fi
  return 1
}

TARGETS=()
KEPT=()
if [ -d "$CLAUDE_DIR" ]; then
  for p in "$CLAUDE_DIR"/* "$CLAUDE_DIR"/.[!.]*; do
    [ -e "$p" ] || continue
    n="${p##*/}"
    if kept "$n"; then KEPT+=("$n"); else TARGETS+=("$p"); fi
  done
fi
for f in "$HOME/.claude.json" "$HOME/.claude.json.backup" "$HOME/.jigkit/skill-usage.jsonl"; do
  if [ -e "$f" ]; then TARGETS+=("$f"); fi
done

# 옆에 클론이 있으면 그것을 쓴다. 없으면 --clone-to 로 받는다.
ROOT=""
if [ -x "$SELF_DIR/bootstrap.sh" ] && [ -x "$SELF_DIR/bin/jig" ]; then
  ROOT="$SELF_DIR"
elif [ -x "$CLONE_TO/bootstrap.sh" ] && [ -x "$CLONE_TO/bin/jig" ]; then
  ROOT="$CLONE_TO"
fi
if [ -n "$ROOT" ]; then
  for d in "$ROOT/build" "$ROOT/library/cache"; do
    if [ -d "$d" ]; then TARGETS+=("$d"); fi
  done
fi

# ---------------------------------------------------------------- 계획
echo
echo "지운다:"
if [ ${#TARGETS[@]} -eq 0 ]; then
  echo "    (없다 — 이미 깨끗하다)"
else
  for t in "${TARGETS[@]}"; do
    case "$t" in
      "$HOME"/*) printf '    ~%s\n' "${t#$HOME}" ;;
      *)         printf '    %s\n' "$t" ;;
    esac
  done
fi
echo
echo "남긴다:"
[ ${#KEPT[@]} -gt 0 ] && printf '    ~/.claude/%s\n' "${KEPT[@]}"
echo "    로그인 상태 (자격증명은 건드리지 않는다)"
echo "    claude 실행 파일, 셸 rc 의 PATH 줄"
echo
echo "그 다음:"
if [ "$DO_BOOTSTRAP" -eq 1 ]; then
  if [ -n "$ROOT" ]; then
    echo "    $ROOT/bootstrap.sh ${BOOTSTRAP_ARGS[*]:-}"
  else
    echo "    git clone $REPO_URL $CLONE_TO"
    echo "    $CLONE_TO/bootstrap.sh ${BOOTSTRAP_ARGS[*]:-}"
  fi
else
  echo "    (--no-bootstrap — 세팅은 하지 않는다)"
fi
echo

if [ "$DRY" -eq 1 ]; then
  echo "--dry-run — 아무것도 하지 않았다."
  echo
  exit 0
fi

confirm "진행할까? (백업은 $BACKUP_DIR 에 남는다)"
echo

# ---------------------------------------------------------------- 실행
make_backup "reset"

if [ ${#TARGETS[@]} -gt 0 ]; then
  rm -rf "${TARGETS[@]}"
  ok reset "${#TARGETS[@]}개 삭제"
else
  skip reset "지울 것이 없었다"
fi
mkdir -p "$CLAUDE_DIR"

if [ "$DO_BOOTSTRAP" -eq 0 ]; then
  echo
  echo "  초기화만 했다. 세팅: <jigkit>/bootstrap.sh"
  echo "  되돌리기: $0 --restore ${BACKUP_FILE:-<백업파일>}"
  echo
  exit 0
fi

if [ -z "$ROOT" ]; then
  if [ -e "$CLONE_TO" ]; then
    fail clone "$CLONE_TO 가 이미 있는데 jigkit 클론이 아니다. --clone-to 로 다른 경로를 준다."
    exit 1
  fi
  if ! git clone --quiet "$REPO_URL" "$CLONE_TO"; then
    fail clone "$REPO_URL 를 받지 못했다"
    exit 1
  fi
  ROOT="$CLONE_TO"
  ok clone "$ROOT"
else
  ok jigkit "$ROOT"
fi

echo
if [ ${#BOOTSTRAP_ARGS[@]} -gt 0 ]; then
  "$ROOT/bootstrap.sh" "${BOOTSTRAP_ARGS[@]}"
else
  "$ROOT/bootstrap.sh"
fi

# ---------------------------------------------------------------- 다음 할 일
cat <<EOF
  다음:

    1. claude                     # 처음 실행 — 로그인·테마·신뢰 프롬프트를 다시 묻는다
    2. cd $ROOT && jig list       # 프로필 목록
    3. jig <profile> <project>    # 그 프로필로 세션 시작

  되돌리기:  $0 --restore ${BACKUP_FILE:-<백업파일>}

EOF
