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

# 새 CLI 표면 검사가 보는 파일. `adapters/` 전체가 아니다 — sources.py 의 git 플래그,
# build.py·cli.py 의 claude 기동 인자처럼 **jig 표면이 아닌 플래그**가 많이 산다.
# cmd 디스패치와 명령 표가 사는 이 둘이 jig 표면의 전부다. bin/jig 가 bash 로 직접
# 처리하는 `new`·`help` 는 못 본다 — 알고 감수하는 한계다.
CLI_SURFACE_PATHS = ["adapters/claude/cli.py", "adapters/commands.py"]

# 표면 검사용 플래그 매처. 산문 스캔의 _FLAG 는 소음 때문에 3자 하한을 두지만,
# 존재 판정에 하한을 두면 `--as` 같은 짧은 새 플래그가 조용히 빠진다.
_FLAG_ANY = re.compile(r"--([a-z][a-z0-9-]*)")

# jig 가 플래그를 **소비하는** 이디엄. cli.py 에는 claude 기동 argv 의 `--플래그`
# 리터럴도 살기 때문에, 소비 지점에 앵커하지 않으면 남의 표면까지 검사하게 된다 —
# 그걸 수동 제외 목록(SURFACE_STOP)으로 막았었는데, 목록은 새 기동 인자마다 편집
# 세금이 들고 낡은 항목이 미래의 진짜 jig 플래그를 영구 면제한다. 앵커가 목록을
# 대체한다. 이디엄이 바뀌면 selftest 의 플래그 카나리아가 잡는다.
_JIG_FLAG_LINE = re.compile(r"_flag_value\(|in rest\b")

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


def code_diff(rev_range: str | None = None, paths: list[str] | None = None) -> str:
    """staged diff (기본) 또는 지정한 리비전 범위의 diff. 코드 경로만.

    paths 는 pathspec 커밋의 판정 범위 — git pathspec 은 합집합이라 CODE_PATHS 와
    한 호출로 교집합할 수 없으므로, 이름을 먼저 좁히고 그 파일들만 diff 한다.
    """
    base = ["diff", "-U0", rev_range or "--cached"]
    if paths is None:
        return _git(*base, "--", *CODE_PATHS)
    names = _git("diff", "--name-only", rev_range or "--cached", "--", *paths).splitlines()
    inside = [n for n in names if any(n == p or n.startswith(p + "/") for p in CODE_PATHS)]
    return _git(*base, "--", *inside) if inside else ""


def _doc_paths(names: list[str]) -> list[str]:
    """staged 목록에서 "문서를 봤다" 로 인정할 파일만.

    CHANGELOG.md 는 뺀다 — 이력은 현재 상태의 서술이 아니다. 이력 한 줄로 게이트가
    조용해지는 길을 열면, 알려진 약점("아무 .md 하나면 통과")이 정문이 된다.
    """
    return [f for f in names if f.endswith(".md") and f != "CHANGELOG.md"]


def staged_docs(worktree: bool = False, paths: list[str] | None = None) -> list[str]:
    """"문서를 봤다" 로 인정할 변경 목록. worktree 는 `commit -a`·pathspec 용 —
    그 커밋에 실리는 것은 index 가 아니라 추적 중인 작업트리고, pathspec 이 있으면
    그 밖의 dirty 문서는 커밋에 안 실리므로 증거가 아니다."""
    base = ["diff", "HEAD", "--name-only"] if worktree else ["diff", "--cached", "--name-only"]
    if worktree and paths:
        base += ["--", *paths]
    return _doc_paths(_git(*base).splitlines())


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


def _surface_tokens(diff: str) -> dict[str, str]:
    """diff 의 `+` 줄이 만든 CLI 표면 토큰 -> 근거. 문서를 읽기 전의 싼 전반부다."""
    current = ""
    found: dict[str, str] = {}
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            current = raw[4:].strip()
            current = current[2:] if current.startswith("b/") else current
            continue
        if current not in CLI_SURFACE_PATHS:
            continue
        if not raw.startswith("+") or raw.startswith("++"):
            continue
        line = raw[1:]
        for m in _CMDLIT.finditer(line):
            # STOP·길이 필터를 걸지 않는다 — 그건 산문 스캔의 소음 필터고 여기는
            # 존재 판정이다. `cmd == "test"` 는 이름이 STOP 에 있어도 새 명령이다.
            found.setdefault(m.group(1), f"명령 jig {m.group(1)}")
        # 플래그는 소비 이디엄이 있는 줄에서만 — commands.py 의 표는 그 자체가 표면.
        if current == "adapters/commands.py" or _JIG_FLAG_LINE.search(line):
            for m in _FLAG_ANY.finditer(line):
                found.setdefault("--" + m.group(1), "플래그")
    return found


def undocumented_surface(diff: str, doc_texts: list[str]) -> list[tuple[str, str]]:
    """추가된 CLI 표면 중 어떤 primary 문서에도 없는 것 -> [(토큰, 근거)].

    기존 게이트는 "기존 문서가 언급하는 개념을 바꿨는가" 만 본다. 그래서 **처음
    생기는** 명령·플래그는 언급하는 문서가 없어 조용히 통과했다 — 여기는 반대
    방향을 본다: `+` 줄이 만든 표면이 문서 어딘가에 존재하는가.

    길잡이가 아니라 존재 판정이므로 TOO_COMMON 상한은 적용하지 않는다. 이동된
    코드(지웠다가 다시 붙인 줄)는 이미 문서에 있으므로 존재 판정이 자연히 거른다.
    """
    found = _surface_tokens(diff)
    out: list[tuple[str, str]] = []
    for tok, why in sorted(found.items()):
        # 양쪽 다 맨 토큰으로 본다 — 문서의 `jig served` 가 `serve` 를, 문서의
        # `--output-format` 이 `--out` 을 증명하면 안 된다.
        if tok.startswith("--"):
            pat = re.compile(rf"(?<![\w-]){re.escape(tok)}(?![\w-])")
        else:
            pat = re.compile(rf"jig {re.escape(tok)}(?![\w-])")
        if not any(pat.search(text) for text in doc_texts):
            out.append((tok, why))
    return out


def new_cli_surface(rev_range: str | None = None, worktree: bool = False,
                    diff: str | None = None,
                    paths: list[str] | None = None) -> list[tuple[str, str]]:
    """게이트용 래퍼. 어떤 오류에서도 [] — fail-open, 게이트 본체와 같은 방향.

    문서를 읽는 곳이 모드를 따라간다 — 판정 대상이 "**이 커밋에** 문서가 실리는가"
    이기 때문이다.
      staged   : index 만. 디스크 폴백을 두면 stage 안 된 서술이 표면을 "증명"한다.
      worktree : `commit -a`·pathspec 용. 추적 중인 디스크 파일 — 단, pathspec 밖의
                 dirty 문서는 그 커밋에 실리지 않으므로 HEAD 내용으로 되돌려 본다.
                 미추적 문서도 증거가 아니다.
      rev_range: 자문용(jig touched). 디스크로 충분하다.

    diff 는 호출자가 이미 만들었다면 건넨다 (게이트가 두 번 돌리지 않게).
    표면 토큰이 아예 없으면 문서를 읽기 전에 끝낸다 — 대부분의 커밋은 표면 파일을
    건드리지 않는데 그때마다 문서 수만큼 subprocess 를 돌릴 이유가 없다.
    """
    try:
        if diff is None:
            diff = code_diff("HEAD" if worktree else rev_range, paths=paths)
        if not diff.strip() or not _surface_tokens(diff):
            return []
        texts: list[str] = []
        if worktree:
            tracked = set(_git("ls-files").splitlines())
            dirty = set(_git("diff", "HEAD", "--name-only").splitlines())
            shipped = (set(_git("diff", "HEAD", "--name-only", "--", *paths).splitlines())
                       if paths else dirty)
        for f in doc_files()[0]:
            rel = str(f.relative_to(HARNESS))
            if worktree:
                if rel not in tracked:
                    continue
                if rel in dirty and rel not in shipped:
                    text = _git("show", f"HEAD:{rel}")  # 커밋에 안 실리는 편집 제외
                else:
                    try:
                        text = f.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
            elif rev_range is None:
                text = _git("show", f":{rel}")
            else:
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
            if text:
                texts.append(text)
        return undocumented_surface(diff, texts)
    except Exception:
        return []


def report(rev_range: str | None = None,
           surface: list[tuple[str, str]] | None = None,
           diff: str | None = None) -> tuple[str, bool]:
    """(출력 문자열, primary 히트가 있는가).

    표면 검사와 diff 를 이미 만들었으면 건넨다 — 게이트가 커밋마다 같은 subprocess
    를 두 번씩 돌리지 않게. None 이면 여기서 계산한다.
    """
    if diff is None:
        diff = code_diff(rev_range)
    if not diff.strip():
        watched = " · ".join(CODE_PATHS)
        return (f"코드 변경이 없다 ({watched}).", False)

    tokens = extract_tokens(diff)
    primary_files, historical_files = doc_files()
    p_hits = scan(tokens, primary_files)
    h_hits = scan(tokens, historical_files)
    if surface is None:
        surface = new_cli_surface(rev_range, diff=diff)

    if not p_hits and not h_hits and not surface:
        return ("바뀐 개념을 언급하는 문서가 없다.", False)

    # 차단 판단은 게이트가 new_cli_surface() 를 직접 호출한다 — 여기는 표시만.
    # 그래서 반환되는 has_primary 의 의미는 표면 검사와 무관하게 그대로다.
    if surface:
        # 과거 범위(rev_range)는 이미 지나간 커밋이다 — 막는다고 말하면 거짓이다.
        note = "커밋 게이트가 막는다" if rev_range is None else "이 범위에서는 안 막혔다 — 참고"
        head = [f"새 CLI 표면 — 어떤 primary 문서에도 없다 ({note})", ""]
        for tok, why in surface:
            head.append(f"    {tok}    ({why})")
        head.append("")
        if not p_hits and not h_hits:
            return ("\n".join(head), False)
    else:
        head = []

    lines = head + ["이 변경이 건드린 개념을 언급하는 문서", ""]

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
