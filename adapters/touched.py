#!/usr/bin/env python3
"""이 변경이 건드린 개념을 언급하는 문서를 찾아 준다.

**판정하지 않는다.** 문서가 맞는지는 기계가 알 수 없다. 이 모듈이 하는 일은
"네가 바꾼 것을 문서 어디서 말하고 있는지" 목록을 만들어 주는 것뿐이고,
읽고 판단하는 것은 호출자다. 그래서 이름이 `check` 가 아니라 `touched` 다 —
실패하지 않는 것을 check 라 부르면 깨끗한 출력이 승인으로 읽힌다.

핵심 어려움 하나: **코드는 식별자로 말하고 문서는 개념으로 말한다.**
`cmd_usage` 로 문서를 훑으면 아무것도 안 잡힌다. `usage` 로 훑어야 잡힌다.
그래서 식별자를 밑줄로 쪼개 개념 후보를 함께 만든다.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]

# 변경을 볼 경로.
#
# `adapters`·`bin`·`bootstrap.sh` 만으로 시작했는데 그건 너무 좁았다 — 프로필의
# inputs/outputs 는 README 의 핸드오프 표에 그대로 적혀 있고, core 의 PREAMBLE·
# /profile 스킬도 문서가 서술한다. 그쪽 변경이 문서와 어긋나도 게이트가 못 봤다.
# `library/cache/` 는 gitignore 라 여기 들어와도 diff 가 안 생긴다.
CODE_PATHS = ["adapters", "bin", "bootstrap.sh", "profiles", "core", "library"]

# 갱신 대상인 문서. 여기 히트가 있는데 문서를 하나도 안 건드렸으면 게이트가 막는다.
PRIMARY = [
    "README.md", "README.ko.md", "PRINCIPLES.md", "CLAUDE.md",
    "core/PREAMBLE.md", "core/skills/profile/SKILL.md", "library/mcp/README.md",
]
PRIMARY_GLOBS = ["profiles/*/BRIEF.md"]

# 과거 실측 기록. 매번 최신화할 대상이 아니다 — 보여는 주되 게이트 판단에서는 뺀다.
HISTORICAL_GLOBS = ["probe/results/*.md"]

# 히트가 이보다 많은 토큰은 너무 일반적이라 길잡이가 못 된다.
TOO_COMMON = 12

# 출력 상한. 다 보여주면 아무도 안 읽는다 — 소음 도구가 되는 지점이다.
MAX_GROUPS = 8
MAX_HITS = 6

# 처음부터 버린다. 시험 추출에서 실제로 섞여 나온 것들이다.
STOP = {
    "print", "sort", "sorted", "json", "path", "return", "self", "none", "true",
    "false", "list", "dict", "str", "int", "bool", "file", "files", "line", "lines",
    "text", "name", "names", "data", "value", "values", "read", "write", "open",
    "resolve", "parent", "exists", "is_dir", "is_file", "mkdir", "home", "encoding",
    "utf-8", "main", "args", "rest", "cmd", "out", "get", "set", "add", "run",
    "test", "tests", "code", "type", "with", "from", "import", "class", "def",
    "for", "not", "and", "the", "this", "that", "size", "count", "total", "item",
    "items", "key", "keys", "part", "parts", "root", "dir", "dirs", "tmp", "log",
}

_DEF = re.compile(r"^[+-]\s*def\s+([a-z_][a-z0-9_]*)", re.I)
_CMDLIT = re.compile(r'cmd == "([a-z-]+)"')
_FLAG = re.compile(r"--([a-z][a-z0-9-]{2,})")
_FILEISH = re.compile(r"[\w.-]*[\w-]+\.(?:jsonl|json|md|ya?ml|py|sh|txt)\b")
_DOTDIR = re.compile(r"(?<![\w.])\.([a-z][a-z0-9_-]{2,})\b")
_STRLIT = re.compile(r'"([a-z][a-z0-9_./-]{5,})"')
# 확장자 없는 경로 세그먼트. 프로필의 `docs/decisions/{slug}.md` 를 바꿔도 토큰이 안
# 나오던 구멍을 메운다 — 파일명 부분은 `.md` 필터에 걸려 버려지므로 디렉터리를 잡아야
# README 핸드오프 표(`docs/decisions/…`)에 닿는다.
_PATHSEG = re.compile(r"(?<![\w./-])([a-z][\w-]*/[a-z][\w-]*)")


def _git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=str(HARNESS),
                          capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else ""


def code_diff(rev_range: str | None = None) -> str:
    """staged diff (기본) 또는 지정한 리비전 범위의 diff. 코드 경로만."""
    base = ["diff", "-U0"]
    if rev_range:
        base.append(rev_range)
    else:
        base.append("--cached")
    return _git(*base, "--", *CODE_PATHS)


def staged_docs() -> list[str]:
    out = _git("diff", "--cached", "--name-only")
    return [f for f in out.splitlines() if f.endswith(".md")]


def _segments(identifier: str) -> list[str]:
    """`usage_log_path` -> ['usage_log_path', 'usage'].

    문서는 `cmd_usage` 라고 쓰지 않고 `usage` 라고 쓴다. 그래서 식별자 자체와
    밑줄 조각을 함께 후보로 낸다. 히트가 없는 후보는 뒤에서 저절로 사라진다.
    """
    out = [identifier]
    out += [s for s in identifier.split("_") if len(s) >= 4]
    return out


def extract_tokens(diff: str) -> dict[str, set[str]]:
    """개념 토큰 -> 그것을 만들어 낸 코드 근거.

    **신호는 삭제된 줄에 있다.** 뭔가 지워졌다는 것은 "참이던 게 더 이상 참이 아니다"
    라는 뜻이고, 그게 문서가 낡는 이유다. 반대로 새 파일은 전부 `+` 줄이라 내부
    식별자를 몽땅 쏟아내는데, 새 모듈의 내부 이름은 기존 문서 서술과 대응하지 않는다.
    실제로 돌려 보니 그것 하나로 110곳이 나왔다 — 아무도 안 읽는 양이다.

    그래서 비대칭으로 본다.
      `-` 줄 : 모든 규칙 (사라지거나 바뀐 것)
      `+` 줄 : **CLI 표면만** (새로 생긴 명령·플래그는 문서화 대상이다)
    """
    found: dict[str, set[str]] = {}

    def emit(token: str, why: str) -> None:
        # 선행 `.` 과 `-` 는 **벗기지 않는다.** 벗기면 `.jigkit` -> `jigkit`,
        # `--project` -> `project` 가 되어 산문 아무 데나 걸리는 소음 토큰이 된다.
        t = token.rstrip("./-").strip()
        if len(t) < 4 or t.lower() in STOP:
            return
        # 문서 파일명은 신호가 아니다 — 문서가 문서 이름을 언급하는 건 당연하다.
        if t.endswith(".md"):
            return
        found.setdefault(t, set()).add(why)

    def cli_surface(line: str) -> None:
        for m in _CMDLIT.finditer(line):
            emit(m.group(1), f"명령 jig {m.group(1)}")
        for m in _FLAG.finditer(line):
            emit("--" + m.group(1), "플래그")

    for raw in diff.splitlines():
        if not raw or raw[0] not in "+-" or raw[:2] in ("++", "--"):
            continue
        line = raw[1:]

        if raw[0] == "+":
            cli_surface(line)          # 새 CLI 표면만
            continue

        cli_surface(line)              # 이하 삭제된 줄 — 전부 본다
        if m := _DEF.match(raw):
            for seg in _segments(m.group(1)):
                emit(seg, f"함수 {m.group(1)}")
        for m in _FILEISH.finditer(line):
            emit(m.group(0), "파일")
        for m in _DOTDIR.finditer(line):
            emit("." + m.group(1), "경로")
        for m in _PATHSEG.finditer(line):
            emit(m.group(1), "경로")
        for m in _STRLIT.finditer(line):
            emit(m.group(1), "문자열")

    return found


def doc_files() -> tuple[list[Path], list[Path]]:
    primary = [HARNESS / p for p in PRIMARY if (HARNESS / p).is_file()]
    for g in PRIMARY_GLOBS:
        primary += sorted(HARNESS.glob(g))
    historical: list[Path] = []
    for g in HISTORICAL_GLOBS:
        historical += sorted(HARNESS.glob(g))
    return primary, historical


def scan(tokens: dict[str, set[str]], files: list[Path]) -> dict[str, list[tuple]]:
    """토큰 -> [(상대경로, 줄번호, 줄내용)]. 파일을 한 번만 읽는다."""
    hits: dict[str, list[tuple]] = {t: [] for t in tokens}
    for f in files:
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        rel = f.relative_to(HARNESS)
        for i, line in enumerate(lines, 1):
            for t in tokens:
                if t in line:
                    hits[t].append((str(rel), i, line.strip()))
    # 너무 흔한 토큰은 길잡이가 못 된다.
    return {t: h for t, h in hits.items() if h and len(h) <= TOO_COMMON}


def report(rev_range: str | None = None) -> tuple[str, bool]:
    """(출력 문자열, primary 히트가 있는가)."""
    diff = code_diff(rev_range)
    if not diff.strip():
        watched = " · ".join(CODE_PATHS)
        return (f"코드 변경이 없다 ({watched}).", False)

    tokens = extract_tokens(diff)
    primary_files, historical_files = doc_files()
    p_hits = scan(tokens, primary_files)
    h_hits = scan(tokens, historical_files)

    if not p_hits and not h_hits:
        return ("바뀐 개념을 언급하는 문서가 없다.", False)

    lines = ["이 변경이 건드린 개념을 언급하는 문서", ""]

    # **히트가 적은 토큰부터.** 정확한 토큰(`.jigkit` 4곳)이 넓은 토큰(`usage` 14곳)보다
    # 길잡이로 낫다. 많은 순으로 두면 소음이 맨 위에 온다.
    ranked = sorted(p_hits, key=lambda t: (len(p_hits[t]), t))
    for t in ranked[:MAX_GROUPS]:
        why = ", ".join(sorted(tokens[t]))
        lines.append(f"  {t}    ({why})")
        for rel, no, text in p_hits[t][:MAX_HITS]:
            lines.append(f"    {rel}:{no}".ljust(28) + text[:76])
        if len(p_hits[t]) > MAX_HITS:
            lines.append(f"    … 외 {len(p_hits[t]) - MAX_HITS}곳")
        lines.append("")

    if len(ranked) > MAX_GROUPS:
        rest = ", ".join(ranked[MAX_GROUPS:])
        lines.append(f"  (넓은 토큰 생략: {rest})")
        lines.append("")

    if h_hits:
        files = sorted({rel for hs in h_hits.values() for rel, _, _ in hs})
        n = sum(len(v) for v in h_hits.values())
        lines.append(f"  참고 — 과거 실측 기록 {n}곳 ({', '.join(files)}).")
        lines.append("  갱신 대상이 아닐 수 있어 게이트 판단에서는 뺐다.")
        lines.append("")

    total = sum(len(v) for v in p_hits.values())
    lines.append(f"  primary {total}곳. 판정하지 않는다 — 읽고 판단하는 것은 호출자다.")
    return ("\n".join(lines), bool(p_hits))
