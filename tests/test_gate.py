#!/usr/bin/env python3
"""커밋 게이트·기동 게이트와 문서 라우팅의 단위 검사.

**false negative 가 이 장치의 진짜 위험이다.** 게이트가 안 뜨면 아무 일도 안 일어난
것처럼 보이고, 그래서 조용히 무력화된 상태를 아무도 눈치채지 못한다. golden 은
컴파일러만 보고 probe 는 "가능한가" 만 증명한다 — 회귀를 잡는 건 여기다.

의존성 없이 돈다: `python3 tests/test_gate.py` 또는 `jig selftest`.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "adapters"))

import commands  # noqa: E402
import launchgate  # noqa: E402
import touched  # noqa: E402


def _load_bin(alias: str, name: str):
    """`bin/` 스크립트는 확장자가 없어 로더를 직접 지정해야 한다."""
    loader = importlib.machinery.SourceFileLoader(alias, str(ROOT / "bin" / name))
    spec = importlib.util.spec_from_loader(alias, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)      # __name__ 이 alias 라 main() 은 돌지 않는다
    return mod


gate = _load_bin("gate", "jig-commit-gate")
note = _load_bin("note", "jig-pending-note")

_failures: list[str] = []


def check(name: str, got, want) -> None:
    if got != want:
        _failures.append(f"{name}\n    기대: {want!r}\n    실제: {got!r}")


# ---------------------------------------------------------------- 트리거

# 여기가 뚫리면 게이트가 통째로 조용해진다. 놓치는 쪽이 훨씬 비싸므로 넉넉히 잡는다.
for cmd in [
    "git commit -m x",
    'git commit -m "여러 단어"',
    "git -c user.name=x commit -m y",          # 전역 -c
    "git -C /some/path commit",                # 전역 -C
    "git --no-pager commit",                   # 전역 --옵션
    "git\tcommit -m x",                        # 탭 구분
    "cd foo && git commit -m x",               # 체이닝
    "git add -A; git commit -m x",             # 세미콜론
    "(git commit)",                            # 서브셸
    "git --git-dir .git commit",               # 값이 분리된 전역 옵션
    "git --work-tree /tmp/x commit -m y",
    'git -C "/path with space" commit',        # 따옴표 안의 공백
    "/usr/bin/git commit -m x",                # 절대경로 호출
    "JIG_TOUCHED_BYPASS_TYPO=1 git commit",    # 오타난 우회는 우회가 아니다
    'git commit -m "docs: A && B"',            # 따옴표 안의 operator
    'git commit -m "fix #12 (urgent)"',        # `#` 는 주석이 아니다
]:
    check(f"트리거: {cmd!r}", gate.is_git_commit(cmd), True)

for cmd in [
    "git status",
    "git add -A",
    "git commit-tree abc",                     # plumbing 은 대상이 아니다
    "gitk commit",                             # git 이 아니다
    "legit commit",
    "",
]:
    check(f"비트리거: {cmd!r}", gate.is_git_commit(cmd), False)

# 우회는 빡빡하게. 느슨하면 게이트가 의도치 않게 꺼지고, 꺼진 것은 티가 안 난다.
for cmd in [
    "JIG_TOUCHED_BYPASS=1 git commit -m x",
    "cd foo && JIG_TOUCHED_BYPASS=1 git commit -m x",
    "JIG_TOUCHED_BYPASS=1 git --git-dir .git commit",   # 분리된 옵션 인자와 함께
    # 따옴표 안의 operator 때문에 탈출구가 거절되면 안 된다.
    'JIG_TOUCHED_BYPASS=1 git commit -m "docs: explain A && B"',
    'JIG_TOUCHED_BYPASS=1 git commit -m "docs: A; B"',
    'JIG_TOUCHED_BYPASS=1 git commit -m "fix #12 (urgent)"',
]:
    check(f"우회 인식: {cmd!r}", gate.is_bypassed(cmd), True)

# shell 의미론상 `VAR=1 cmd` 는 **그 단순 명령에만** 붙는다. 세그먼트를 넘어가면
# 우회가 아니다 — 여기가 느슨하면 게이트가 조용히 꺼진다.
for cmd in [
    "git commit -m x",
    "echo JIG_TOUCHED_BYPASS; git commit -m x",         # 대입이 아니다
    'git commit -m "JIG_TOUCHED_BYPASS=1 을 다룬다"',     # 커밋 메시지 안의 언급
    "git commit -m x && JIG_TOUCHED_BYPASS=1 echo hi",   # commit 뒤에 온다
    "JIG_TOUCHED_BYPASS=1 echo hi; git commit -m x",     # 다른 명령에 붙었다
    "JIG_TOUCHED_BYPASS=1 echo git commit",              # 실제 git 실행이 아니다
    "git --git-dir .git commit && JIG_TOUCHED_BYPASS=1 echo hi",  # 모델이 갈라지던 자리
]:
    check(f"우회 아님: {cmd!r}", gate.is_bypassed(cmd), False)

# `-a`·pathspec 커밋은 훅 시점의 index 가 비어 있어도 커밋 시점에 작업트리를
# stage 한다 — index 만 보면 `-am` 한 방에 게이트 전체가 조용히 우회된다(리뷰에서
# 확인된 구멍). 오인 방향도 지킨다: `-m` 의 메시지 값을 pathspec 으로 읽으면
# 모든 커밋이 작업트리 모드가 된다.
for cmd in [
    "git commit -a -m x",
    "git commit -am x",                        # 뭉친 짧은 옵션
    "git commit --all -m x",
    "git commit -m x file.py",                 # pathspec
    "git commit -m x -- docs/a.md",            # `--` 뒤는 전부 pathspec
    "git commit --include foo.py -m x",
    "git commit --include=foo.py -m x",        # `=` 형태도 같은 옵션이다
    "git commit --pathspec-from-file=list.txt -m x",
    "git commit --pathspec-from-file list.txt -m x",
    "git commit --frobnicate -m x",            # 모르는 옵션 — fail-closed 로 넓힌다
    # git 은 -u 값을 `=` 붙임꼴로만 받는다 — foo.py 를 값으로 삼키면 index 오판
    "git commit --untracked-files foo.py -m x",
]:
    check(f"작업트리 판정: {cmd!r}", gate.widens_worktree(cmd), True)

for cmd in [
    "git commit -m x",
    'git commit -m "a b c"',                   # 메시지 값은 pathspec 이 아니다
    'git commit -m"fix: x"',                   # 붙은 값 — 메시지 글자는 옵션이 아니다
    "git commit -mdocs",
    "git commit --amend -m x",                 # amend 는 index 기준
    "git commit --amend --no-edit",
    "git commit -s -v -m x",
    "git commit -S -m x",                      # -S[keyid] 는 값이 붙는 옵션
    "git commit -F msg.txt",                   # 값 옵션의 값도 pathspec 이 아니다
    "git commit --message=x",
]:
    check(f"index 판정: {cmd!r}", gate.widens_worktree(cmd), False)

# pathspec 은 판정 범위를 좁히는 데 쓴다 — 커밋에 안 실리는 무관한 dirty 파일이
# 게이트를 잠재우면 안 된다. None 은 전체 작업트리(또는 비확장 커밋).
check("pathspec 추출",
      gate.commit_pathspec("git commit -m x foo.py bar.py"), ["foo.py", "bar.py"])
check("`--` 뒤 pathspec 추출",
      gate.commit_pathspec("git commit -m x -- docs/a.md"), ["docs/a.md"])
check("`-a` 는 전체 작업트리", gate.commit_pathspec("git commit -am x"), None)
check("비확장 커밋은 범위 없음", gate.commit_pathspec("git commit -m x"), None)

# 우회된 호출의 형태는 다른 호출의 판정에 전염되지 않는다 — 우회한 `-am` 이
# 뒤따르는 index 커밋을 작업트리 기준으로 읽게 만들면 오발·누락 양쪽이 열린다.
check("우회된 -am 은 뒤 커밋의 판정 범위를 넓히지 않는다",
      gate.widens_worktree(
          "JIG_TOUCHED_BYPASS=1 git commit -am wip && git commit -m fix"), False)
check("우회 없는 -am 은 체이닝 속에서도 넓힌다",
      gate.widens_worktree("git add -A; git commit -am x"), True)

# pathspec 은 명령이 도는 cwd 기준이다 — touched 는 루트에서 diff 를 돌리므로
# 루트 기준으로 바꿔야 한다. 하위 디렉터리 커밋에서 그대로 쓰면 아무것도 안 맞아
# 게이트가 조용히 꺼진다. 확신이 없으면 전체 작업트리 (fail-closed).
check("하위 디렉터리 pathspec 을 루트 기준으로 해석한다",
      gate._resolve_pathspec(["cli.py"], "/repo/adapters/claude", "/repo"),
      ["adapters/claude/cli.py"])
check("루트에서는 그대로",
      gate._resolve_pathspec(["adapters/touched.py"], "/repo", "/repo"),
      ["adapters/touched.py"])
check("루트 밖으로 나가면 전체로 넓힌다",
      gate._resolve_pathspec(["../x.py"], "/repo", "/repo"), None)
check("매직 pathspec 은 해석하지 않고 전체로 넓힌다",
      gate._resolve_pathspec([":(glob)**/*.py"], "/repo", "/repo"), None)

# ---------------------------------------------------------------- 토큰 추출

DIFF_REMOVED = """\
--- a/bin/jig-log-skill
+++ b/bin/jig-log-skill
-    out = Path(cwd) / ".harness" / "skill-usage.jsonl"
+    out = log_path()
"""
tok = touched.extract_tokens(DIFF_REMOVED)
check("삭제된 경로가 토큰이 된다", ".harness" in tok, True)
check("삭제된 파일명이 토큰이 된다", "skill-usage.jsonl" in tok, True)

DIFF_NEW_FILE = """\
--- /dev/null
+++ b/adapters/brand_new.py
+def helper_function():
+    total_widget_count = 3
+    return total_widget_count
"""
tok = touched.extract_tokens(DIFF_NEW_FILE)
check("새 파일의 내부 식별자는 토큰이 아니다", tok, {})

DIFF_NEW_CLI = """\
--- a/adapters/claude/cli.py
+++ b/adapters/claude/cli.py
+        elif cmd == "touched":
+    only = _flag_value(rest, "--project")
"""
tok = touched.extract_tokens(DIFF_NEW_CLI)
check("새 CLI 명령은 토큰이 된다", "touched" in tok, True)
check("새 플래그는 토큰이 된다", "--project" in tok, True)

DIFF_STOP = """\
--- a/adapters/x.py
+++ b/adapters/x.py
-    print(sorted(data))
-    path = "README.md"
"""
tok = touched.extract_tokens(DIFF_STOP)
check("일반 토큰은 버린다", [t for t in tok if t in ("print", "sorted", "data")], [])
check("문서 파일명은 토큰이 아니다", "README.md" in tok, False)

check("플래그 접두사를 벗기지 않는다", "project" in touched.extract_tokens(
    '--- a/x\n+++ b/x\n-    v = _flag_value(rest, "--project")\n'), False)

# 프로필의 산출물 경로는 README 핸드오프 표에 그대로 적혀 있다. 파일명(`{slug}.md`)은
# .md 필터에 걸리므로 **디렉터리**를 잡아야 문서에 닿는다.
DIFF_PROFILE = """\
--- a/profiles/developer/profile.yaml
+++ b/profiles/developer/profile.yaml
-  - docs/decisions/{slug}.md
+  - docs/notes/{slug}.md
"""
check("프로필 산출물 경로가 토큰이 된다",
      "docs/decisions" in touched.extract_tokens(DIFF_PROFILE), True)

# ---------------------------------------------------------------- 스캔

check("너무 흔한 토큰은 걸러진다",
      touched.scan({"the": {"x"}}, touched.doc_files()[0]), {})

# ---------------------------------------------------------------- 새 CLI 표면

# 기존 조건은 "기존 문서가 언급하는 개념" 만 봐서 **처음 생기는** 명령·플래그가
# 조용히 통과했다. 존재 판정을 양방향으로 고정한다 — 안 잡히면 게이트가 없는 것과
# 같고(false negative), 오발하면 우회가 습관이 되어 게이트가 죽는다(false positive).

DIFF_SURFACE = """\
--- a/adapters/claude/cli.py
+++ b/adapters/claude/cli.py
+        elif cmd == "serve":
+    x = _flag_value(rest, "--frobnicate")
"""
DOCS_EMPTY = ["# README\n아무 표면도 서술하지 않는 문서"]
got = touched.undocumented_surface(DIFF_SURFACE, DOCS_EMPTY)
check("미문서화 명령이 잡힌다", ("serve", "명령 jig serve") in got, True)
check("미문서화 플래그가 잡힌다", ("--frobnicate", "플래그") in got, True)

check("문서에 있으면 잡히지 않는다 (이동된 코드도 이 경로로 해소)",
      touched.undocumented_surface(
          DIFF_SURFACE, ["`jig serve` 는 서빙한다. `--frobnicate` 플래그."]), [])

# 맨 단어 판정 — 문서의 `jig served` 가 `serve` 를 증명하면 안 된다.
check("부분 문자열은 명령의 증거가 아니다",
      ("serve", "명령 jig serve") in touched.undocumented_surface(
          DIFF_SURFACE, ["jig served 를 설명하는 문서. --frobnicate 플래그."]), True)

check("제거된 표면은 잡지 않는다 (- 줄은 신설이 아니다)",
      touched.undocumented_surface("""\
--- a/adapters/claude/cli.py
+++ b/adapters/claude/cli.py
-        elif cmd == "serve":
-    x = _flag_value(rest, "--frobnicate")
""", DOCS_EMPTY), [])

check("표면 경로 밖(sources.py 의 git 플래그)은 잡지 않는다",
      touched.undocumented_surface("""\
--- a/adapters/sources.py
+++ b/adapters/sources.py
+    args += ["--depth", "1"]
""", DOCS_EMPTY), [])

# 플래그는 jig 의 소비 이디엄(_flag_value·in rest)이 있는 줄에서만 표면이다 —
# claude 기동 argv 의 리터럴은 남의 표면이고, 수동 제외 목록은 낡는다.
check("소비 이디엄이 없는 줄의 플래그(claude 기동 argv)는 잡지 않는다",
      touched.undocumented_surface("""\
--- a/adapters/claude/cli.py
+++ b/adapters/claude/cli.py
+        argv += ["--output-format", "json"]
""", DOCS_EMPTY), [])
check("commands.py 의 표는 그 자체가 표면 — 이디엄 없이도 잡힌다",
      touched.undocumented_surface("""\
--- a/adapters/commands.py
+++ b/adapters/commands.py
+    ("dev", "frob [--zap]", "frob [--zap]", "x", "y"),
""", DOCS_EMPTY),
      [("--zap", "플래그")])

# 접두사 그림자 — 문서의 긴 플래그가 그것을 접두사로 포함하는 짧은 새 플래그를
# 증명하면 안 된다. 리뷰에서 실행으로 확인된 false negative.
DIFF_OUT = """\
--- a/adapters/claude/cli.py
+++ b/adapters/claude/cli.py
+    v = _flag_value(rest, "--out")
"""
check("문서의 --output-format 이 --out 을 증명하지 않는다",
      touched.undocumented_surface(DIFF_OUT, ["--output-format json 을 쓴다"]),
      [("--out", "플래그")])
check("정확히 그 플래그가 문서에 있으면 통과",
      touched.undocumented_surface(DIFF_OUT, ["`--out` 은 출력 경로다"]), [])

# STOP 은 산문 스캔의 소음 필터지 존재 판정의 면제가 아니다 — 이름이 STOP 에 있는
# 짧은 새 명령(`jig test` 류)이 검사를 통째로 빠져나가면 안 된다.
DIFF_TEST_CMD = """\
--- a/adapters/claude/cli.py
+++ b/adapters/claude/cli.py
+        elif cmd == "test":
"""
check("STOP 에 있는 이름의 새 명령도 잡힌다",
      touched.undocumented_surface(DIFF_TEST_CMD, DOCS_EMPTY),
      [("test", "명령 jig test")])
check("STOP 이름이라도 문서화돼 있으면 통과",
      touched.undocumented_surface(DIFF_TEST_CMD, ["jig test 는 검사를 돌린다"]), [])

# 존재 판정에는 산문용 3자 하한이 없다 — `--as` 같은 2자 플래그도 표면이다.
DIFF_SHORT_FLAG = """\
--- a/adapters/claude/cli.py
+++ b/adapters/claude/cli.py
+    v = _flag_value(rest, "--rm")
"""
check("2자 플래그도 잡힌다",
      touched.undocumented_surface(DIFF_SHORT_FLAG, DOCS_EMPTY),
      [("--rm", "플래그")])
check("2자 플래그도 문서에 있으면 통과",
      touched.undocumented_surface(DIFF_SHORT_FLAG, ["`--rm` 은 지운다"]), [])

# 자기 기준선 — 표면 파일 전체를 "신설" 로 간주해도 아무것도 안 잡혀야 한다.
# 소비 이디엄 앵커(_JIG_FLAG_LINE)가 새 claude 기동 인자를 무시하지 못하게 되면
# 커밋 게이트에서 놀라기 전에 **여기가 먼저** 빨간불이 된다.
_primary_texts_disk = [f.read_text(encoding="utf-8") for f in touched.doc_files()[0]]
for _sp in touched.CLI_SURFACE_PATHS:
    _src = (ROOT / _sp).read_text(encoding="utf-8")
    _fake = f"+++ b/{_sp}\n" + "".join(f"+{l}\n" for l in _src.splitlines())
    check(f"자기 기준선: {_sp} 의 표면이 전부 문서화 또는 소비 이디엄 밖",
          touched.undocumented_surface(_fake, _primary_texts_disk), [])

# 카나리아 — 추출 정규식과 실제 디스패치 스타일의 **연결**이 살아 있는가. cli.py 의
# 디스패치를 dict 매핑 등으로 바꾸면 _CMDLIT 는 조용히 아무것도 못 찾게 되고, 합성
# diff 테스트들은 계속 초록불이다. 그 침묵을 여기서 실패로 바꾼다.
# `new` 는 bash(bin/jig)가 처리하는 문서화된 예외다.
_cli_src = (ROOT / "adapters" / "claude" / "cli.py").read_text(encoding="utf-8")
_extracted = set(touched._CMDLIT.findall(_cli_src))
for name in commands.names():
    if name == "new":
        continue
    check(f"카나리아: cli.py 디스패치에서 {name} 이 _CMDLIT 로 추출된다",
          name in _extracted, True)

# 플래그 카나리아 — 소비 이디엄 앵커(_JIG_FLAG_LINE)가 실제 코드와 연결돼 있는가.
# cli.py 가 플래그 파싱 방식을 바꾸면 표의 플래그가 추출에서 빠지고, 그 순간부터
# 새 플래그 검사가 조용히 죽는다 — 그 침묵을 여기서 실패로 바꾼다.
_fake_cli = "+++ b/adapters/claude/cli.py\n" + "".join(
    f"+{l}\n" for l in _cli_src.splitlines())
_flags_extracted = {t for t in touched._surface_tokens(_fake_cli) if t.startswith("--")}
for fl in sorted({"--" + m for _, inv, _, _, _ in commands.COMMANDS
                  for m in re.findall(r"--([a-z][a-z0-9-]*)", inv)}):
    check(f"플래그 카나리아: {fl} 가 cli.py 소비 이디엄에서 추출된다",
          fl in _flags_extracted, True)

# 실저장소 기준선 — 표의 모든 명령이 primary 문서에서 `jig <이름>` 으로 잡혀야
# 이 게이트가 기존 명령에 오발하지 않는다. 표에서 기대값을 파생하므로 명령을
# 추가하면 검사가 저절로 따라온다.
for name in commands.names():
    pat = re.compile(rf"jig {re.escape(name)}(?![\w-])")
    check(f"기준선: jig {name} 이 primary 문서에 있다",
          any(pat.search(t) for t in _primary_texts_disk), True)

msg = gate._surface_message([("serve", "명령 jig serve"), ("--frobnicate", "플래그")])
for needle in ["serve", "--frobnicate", "jig docs --update", "CHANGELOG",
               f"{gate.BYPASS}=1 git commit"]:
    check(f"표면 차단 메시지에 {needle!r} 가 있다", needle in msg, True)

# ---------------------------------------------------------------- staged 문서 필터

# 이력은 "문서를 봤다" 의 증거가 아니다 — CHANGELOG 한 줄로 게이트가 조용해지면
# 알려진 약점("아무 .md 하나면 통과")이 정문이 된다.
check("CHANGELOG 만으로는 문서로 인정되지 않는다",
      touched._doc_paths(["CHANGELOG.md", "README.md", "adapters/x.py"]),
      ["README.md"])
check("빈 목록은 빈 목록", touched._doc_paths([]), [])
check("다른 .md 는 경로 무관하게 인정",
      touched._doc_paths(["probe/results/x.md"]), ["probe/results/x.md"])

# ---------------------------------------------------------------- 실제 사건 회귀

# 이 도구가 존재하는 이유. 전역 전환 커밋(00b089f)에서 `jig usage` 를 문서화한 줄을
# 놓쳤다. **줄 번호로 단언하지 않는다** — 문서가 자라면 번호는 밀린다(실제로 밀렸다).
# 변하지 않는 것은 "그 개념을 설명하는 줄을 짚는가" 다.
text, has_primary = touched.report("00b089f~1..00b089f")
check("놓쳤던 커밋에서 primary 히트가 난다", has_primary, True)
usage_lines = [l for l in text.splitlines() if "jig usage" in l]
check("jig usage 를 문서화한 줄을 짚는다", len(usage_lines) >= 2, True)
for doc in ["README.md:", "docs/ko/README.md:"]:
    check(f"{doc} 을 짚는다", any(doc in l for l in usage_lines), True)
check("소음 토큰이 안 섞인다",
      any(t in text for t in ("\n  print ", "\n  sorted ", "\n  jigkit ")), False)

# 소음 상한이 지켜지는가 — 첫 구현은 110곳을 뱉었고 그건 아무도 안 읽는 양이었다.
groups = [l for l in text.splitlines() if l.startswith("  ") and not l.startswith("    ")]
check("토큰 그룹이 상한 이하", len(groups) <= touched.MAX_GROUPS + 4, True)

# ---------------------------------------------------------------- 사용법·메시지

# 손으로 유지하던 사용법 문자열에서 `selftest` 가 실제로 빠져 있었다. 이제 표에서
# 생성하므로, 명령을 추가하면 자동으로 따라온다 — 그게 유지되는지 본다.
usage = commands.usage_line()
for name in commands.names():
    check(f"사용법에 {name} 이 있다", name in usage, True)

# 감시 경로를 넓혔는데 "코드 변경 없음" 문구가 옛 목록을 말하던 적이 있다.
no_diff, _ = touched.report("HEAD..HEAD")
for p in touched.CODE_PATHS:
    check(f"변경 없음 메시지가 {p} 를 반영한다", p in no_diff, True)

# ---------------------------------------------------------------- 생성물

# `jig docs --check` 상당을 subprocess 없이 직접 돈다. 여기 배선되기 전에는 수동
# 명령으로만 존재해서, 생성 블록이 낡아도 아무것도 알리지 않았다.
try:
    check("생성된 명령 블록이 최신이다 (아니면 `jig docs --update`)",
          commands.apply(write=False), [])
except LookupError as e:
    _failures.append(f"생성 마커를 잃었다 — 복구 없이는 docs --update 가 못 쓴다: {e}")

# ---------------------------------------------------------------- 번역 구조 패리티

# 영문이 정본, 번역은 `docs/<lang>/` — 절 구조 1:1 (CLAUDE.md 의 규칙인데 검사가 없었다).
# 헤딩 텍스트는 번역이라 비교할 수 없다 — **레벨 수열**만 본다. 코드 펜스 안의
# `# bash 주석` 은 헤딩이 아니므로 펜스를 걷어내고 센다.

def _heading_levels(text: str) -> list[int]:
    levels, fenced = [], False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        if not fenced and (m := re.match(r"^(#{1,6}) ", line)):
            levels.append(len(m.group(1)))
    return levels

check("패리티 헬퍼: 펜스 안은 세지 않고 진짜 헤딩은 센다",
      _heading_levels("# a\n```\n### 펜스 안\n```\n## b\n"), [1, 2])

def _canonical_of(translated: Path) -> Path:
    """`docs/<lang>/X.md` 의 정본. README 만 루트에 살고 나머지는 `docs/X.md` 다."""
    return ROOT / "README.md" if translated.name == "README.md" \
        else ROOT / "docs" / translated.name


# 번역 디렉터리를 훑는다 — 언어를 늘려도 검사를 손대지 않는다. 짝이 하나도 안 잡히면
# 그건 통과가 아니라 검사가 죽은 것이다(번역이 옮겨졌는데 조용히 0쌍이 되는 경우).
_pairs = sorted(p for p in (ROOT / "docs").glob("*/*.md"))
check("번역 짝이 하나 이상 잡힌다", len(_pairs) >= 1, True)

for _t in _pairs:
    _rel = _t.relative_to(ROOT)
    _c = _canonical_of(_t)
    if not _c.is_file():
        _failures.append(f"{_rel} 의 정본이 없다: {_c.relative_to(ROOT)}")
        continue
    _tt, _ct = _t.read_text(encoding="utf-8"), _c.read_text(encoding="utf-8")
    check(f"{_rel} 절 구조 1:1 (영문이 정본)",
          _heading_levels(_tt), _heading_levels(_ct))
    check(f"{_rel} 코드 펜스 수 1:1 (영문이 정본)",
          sum(l.startswith("```") for l in _tt.splitlines()),
          sum(l.startswith("```") for l in _ct.splitlines()))

# ---------------------------------------------------------------- 저장소 표식

# 두 훅은 "cwd 의 git 루트가 jigkit 인가" 를 파일 표식으로 판별한다. 표식이 옮겨지면
# 저장소를 못 알아보고 **조용히 통과시킨다** — 게이트가 사라졌는데 화면은 평소와 같다.
# 실제로 PRINCIPLES.md 를 docs/ 로 옮기면서 이 검사가 없어 위험했다.
for _mod, _label in ((gate, "jig-commit-gate"), (note, "jig-pending-note")):
    check(f"{_label}: 이 체크아웃을 jigkit 으로 알아본다",
          _mod.repo_root(str(ROOT)), ROOT)

with tempfile.TemporaryDirectory() as _tmp:
    subprocess.run(["git", "init", "-q", _tmp], check=True)
    for _mod, _label in ((gate, "jig-commit-gate"), (note, "jig-pending-note")):
        check(f"{_label}: 남의 저장소에서는 조용하다",
              _mod.repo_root(_tmp), None)

# ---------------------------------------------------------------- 기동 게이트

# 커밋 게이트와 fail-open 방향이 반대다: 기록 부재는 정상 경로(스킬 미실행·구 스키마)라
# 조용히 통과하고, **기록된 미충족**에만 반응한다. 여기서 지켜야 하는 회귀는 둘 —
# 차단이 조용히 꺼지는 것과, 복구 경로(같은 프로필 재기동)가 막히는 것.

_UNMET = {"profile": "developer", "ts": "2026-08-13T09:00:00+00:00",
          "done": {"passed": 3, "total": 4, "unmet": ["전체 테스트 스위트 미실행"]}}

kind, msg = launchgate.verdict(_UNMET, "reviewer", {})
check("미충족 기록 + 다른 프로필 → 차단", kind, "block")
for needle in ["developer", "3/4", "jig developer",
               f"{launchgate.BYPASS}=1 jig reviewer", "전체 테스트 스위트 미실행"]:
    check(f"차단 메시지에 {needle!r} 가 있다", needle in msg, True)

# 복구 경로 — "돌아가려면 jig developer" 가 막히면 되돌아갈 수 없다.
check("미충족 기록 + 같은 프로필 재기동 → 통과",
      launchgate.verdict(_UNMET, "developer", {})[0], "pass")

# unmet 을 쓰는 쪽은 프롬프트 계층이라 리스트 대신 문자열이 올 수 있다 — 글자
# 단위 ⚠ 도배(실행으로 확인)가 아니라 한 항목으로 나가야 한다.
kind, msg = launchgate.verdict(
    {"profile": "developer",
     "done": {"passed": 3, "total": 4, "unmet": "전체 테스트 스위트 미실행"}},
    "reviewer", {})
check("문자열 unmet 도 차단", kind, "block")
check("문자열 unmet 은 한 항목", msg.count("⚠"), 1)
check("문자열 unmet 내용이 통째로 나간다", "⚠ 전체 테스트 스위트 미실행" in msg, True)
check("이상형 unmet(비문자열·비리스트)은 버리되 차단은 유지",
      launchgate.verdict({"profile": "developer",
                          "done": {"passed": 1, "total": 2, "unmet": 7}},
                         "reviewer", {})[0], "block")

# 전진만 막는다 — next 기록이 있으면 이전 단계 재방문·옆길은 복구 경로다.
_UNMET_NEXT = dict(_UNMET, next="reviewer")
check("next 기록 + 전진(next 로) → 차단",
      launchgate.verdict(_UNMET_NEXT, "reviewer", {})[0], "block")
check("next 기록 + 이전 단계 재방문 → 통과",
      launchgate.verdict(_UNMET_NEXT, "pm", {})[0], "pass")
check("next 없는 기록은 다른 프로필 전부 차단 (방향 불명 — 보수)",
      launchgate.verdict(_UNMET, "pm", {})[0], "block")

# next 를 쓰는 것도 프롬프트 계층이다 — 자기 자신이나 실존하지 않는 프로필을
# 가리키면 "전진 아님" 예외가 모든 프로필을 통과시켜 게이트가 조용히 꺼진다.
check("next 가 자기 자신이면 방향 불명 — 보수 차단",
      launchgate.verdict(dict(_UNMET, next="developer"), "reviewer", {})[0], "block")
check("next 가 실존 프로필이면 known 검사 통과",
      launchgate.verdict(_UNMET_NEXT, "pm", {},
                         known={"developer", "pm", "reviewer"})[0], "pass")
check("next 가 실존하지 않으면 방향 불명 — 보수 차단",
      launchgate.verdict(dict(_UNMET, next="ghost"), "pm", {},
                         known={"developer", "pm", "reviewer"})[0], "block")

# 판정 기록은 기동 사이에 이월된다 — judged 가 주인을 보존해야 프로필이 바뀐
# state 에서도 귀속이 맞는다 (이월 없이는 옆길 기동 한 번에 게이트가 무장해제됐다).
_CARRIED = {"profile": "pm", "judged": "developer", "next": "reviewer",
            "done": {"passed": 3, "total": 4, "unmet": ["전체 테스트 스위트 미실행"]}}
check("이월된 기록: 전진(next) → 차단",
      launchgate.verdict(_CARRIED, "reviewer", {})[0], "block")
check("이월된 기록: 판정 주인 재기동 → 통과 (복구)",
      launchgate.verdict(_CARRIED, "developer", {})[0], "pass")
check("이월된 기록: 옆길 → 통과",
      launchgate.verdict(_CARRIED, "designer", {})[0], "pass")
check("이월된 기록의 차단 메시지가 판정 주인을 가리킨다",
      "jig developer" in launchgate.verdict(_CARRIED, "reviewer", {})[1], True)

# bool 은 int 의 하위 타입이다 — `passed: true` 를 1 로 읽으면 전부 통과한 단계가
# "True/4 미완" 으로 차단된다. 기록으로 인정하지 않는 쪽이 fail-open 방향이다.
check("passed 가 bool 이면 기록으로 인정하지 않는다 → 통과",
      launchgate.verdict({"profile": "developer",
                          "done": {"passed": True, "total": 4}}, "reviewer", {})[0],
      "pass")
check("total 이 bool 이어도 마찬가지",
      launchgate.verdict({"profile": "developer",
                          "done": {"passed": 0, "total": True}}, "reviewer", {})[0],
      "pass")

check("충족 기록(passed == total) → 통과",
      launchgate.verdict({"profile": "developer",
                          "done": {"passed": 4, "total": 4}}, "reviewer", {})[0], "pass")
check("done 없음(스킬 미실행·구 스키마) → 통과",
      launchgate.verdict({"profile": "developer", "next": "reviewer"},
                         "reviewer", {})[0], "pass")
check("state 없음(파일 부재·파싱 실패) → 통과",
      launchgate.verdict(None, "reviewer", {})[0], "pass")
check("이상형 done(passed 누락) → 통과 (fail-open 명시)",
      launchgate.verdict({"profile": "developer", "done": {"total": 4}},
                         "reviewer", {})[0], "pass")
check("이상형 done(비정수) → 통과 (fail-open 명시)",
      launchgate.verdict({"profile": "developer",
                          "done": {"passed": "3", "total": 4}}, "reviewer", {})[0], "pass")

kind, msg = launchgate.verdict(_UNMET, "reviewer", {launchgate.BYPASS: "1"})
check("우회 → bypass", kind, "bypass")
check("우회에도 흔적 메시지가 있다", bool(msg), True)
# 커밋 게이트 검사와 같은 정신 — 오타난 우회는 우회가 아니다.
check("오타난 우회 키 → 차단",
      launchgate.verdict(_UNMET, "reviewer", {launchgate.BYPASS + "_TYPO": "1"})[0],
      "block")
check("빈 값 우회는 우회가 아니다",
      launchgate.verdict(_UNMET, "reviewer", {launchgate.BYPASS: ""})[0], "block")

# ---------------------------------------------------------------- 검증 대기 주입

# 배달 장치는 조용해야 할 곳에서 조용한 것이 계약의 절반이다 — 남의 프로젝트,
# 빈 등록부. 나머지 절반은 jigkit 안에서 내용이 실제로 나가는 것.

check("머리글만 있는 등록부는 0건",
      note.pending_entries("# 검증 대기\n\n규칙 어쩌고\n"), 0)
check("`## ` 헤딩 수가 곧 항목 수",
      note.pending_entries("# t\n## a\n본문\n## b\n"), 2)
check("`###` 는 항목이 아니다", note.pending_entries("### 소제목\n"), 0)
check("코드 펜스 안의 `## ` 는 항목이 아니다",
      note.pending_entries("# t\n```\n## 예시 헤딩\n```\n## 진짜 항목\n"), 1)

import subprocess  # noqa: E402
import tempfile  # noqa: E402

_NOTE_BIN = str(ROOT / "bin" / "jig-pending-note")

with tempfile.TemporaryDirectory() as td:
    proc = subprocess.run([sys.executable, _NOTE_BIN], capture_output=True,
                          text=True, input=f'{{"cwd": "{td}"}}')
    check("jigkit 밖 cwd → 침묵", proc.stdout, "")
    check("jigkit 밖 cwd → exit 0", proc.returncode, 0)

proc = subprocess.run([sys.executable, _NOTE_BIN], capture_output=True,
                      text=True, input="깨진 페이로드")
check("깨진 stdin → exit 0 (세션을 막지 않는다)", proc.returncode, 0)

_PENDING = ROOT / "probe" / "PENDING.md"
proc = subprocess.run([sys.executable, _NOTE_BIN], capture_output=True,
                      text=True, input=f'{{"cwd": "{ROOT}"}}')
if _PENDING.is_file() and note.pending_entries(_PENDING.read_text(encoding="utf-8")):
    check("jigkit 안 + 항목 있음 → 등록부가 나간다",
          "검증 대기" in proc.stdout, True)
else:
    check("항목 없음 → 침묵", proc.stdout, "")

# ---------------------------------------------------------------- 스택 배치
#
# 여기서 잡는 것은 **조용히 어긋나는 배치**다. 훅 항목이 1개라는 사실은 배치가 망가져도
# 그대로 참이므로(실측: probe/results/stack-hooks.md), 모양만 보는 검사로는 부족하다.

import json  # noqa: E402
import tempfile  # noqa: E402

import stacks  # noqa: E402

sys.path.insert(0, str(ROOT / "adapters" / "claude"))
import stack_apply  # noqa: E402

check("카탈로그 로드: 정의가 어긋나지 않는다", bool(stacks.load()[0]), True)

# `--with a,b <경로>` 에서 값이 경로로 잡히면 `<경로>/a,b` 를 대상으로 삼는다. 실행해 봐야
# 나오는 버그였다 — 인자 파싱만 여기서 붙잡는다 (cli 는 import 만 하고 main 은 돌지 않는다).
import cli  # noqa: E402

check("인자: --with 의 값은 위치 인자가 아니다",
      cli.positionals(["api", "--with", "fastapi,logfire", "/tmp/p"], {"--with"}),
      ["api", "/tmp/p"])
check("인자: 값 없는 플래그는 그냥 빠진다",
      cli.positionals(["api", "/tmp/p", "--apply"], {"--with"}), ["api", "/tmp/p"])

_api = stacks.resolve("fastapi")
_web = stacks.resolve("nextjs")
check("alias: fastapi -> api 프리셋", (_api["lang"], _api["label"]), ("python", "api (python)"))
check("alias: 언어 base 가 포함된다",
      {"uv", "ruff", "pyright", "pytest"} <= {i["id"] for i in _api["items"]}, True)
check("프리셋 == 같은 --with 조합",
      [i["id"] for i in _web["items"]],
      [i["id"] for i in stacks.resolve("typescript",
                                       ["next", "prisma", "shadcn", "playwright"])["items"]])
check("dedupe: next 와 nest 를 함께 골라도 biome 은 하나",
      [i["id"] for i in stacks.resolve("typescript", ["next", "prisma"])["items"]].count("biome"),
      1)

# 스캐폴더가 둘이면 어느 쪽이 프로젝트를 만드는지 알 수 없다 — 조용히 하나를 고르면 안 된다.
try:
    stacks.resolve("typescript", ["next", "nest"])
    check("스캐폴더 둘 -> 거부", "통과했다", "StackError")
except stacks.StackError as e:
    check("스캐폴더 둘 -> 거부", "스캐폴더가 둘" in str(e), True)

_target = Path("/tmp/jig-selftest-x")
_steps = stacks.plan(_web, _target)
_plan = [step for step, _ in _steps]
check("--plan 순서", _plan[:2], ["create", "install"])
check("--plan: apply 가 verify 앞에 온다", _plan.index("apply") < _plan.index("verify"), True)
check("--plan: normalize 는 apply 뒤 (설정 파일을 apply 가 놓는다)",
      _plan.index("apply") < _plan.index("normalize"), True)
_cmds = dict(_steps)
check("--plan: apply 단계가 --apply 를 붙인다", _cmds["apply"].endswith("--apply"), True)

# 각 줄은 그 자체로 완결이어야 한다 — 실행기가 줄마다 새 셸을 쓰면 cd 한 줄은 사라진다.
check("--plan: 프로젝트 안에서 돌 줄은 스스로 cd 한다",
      [s for s, c in _steps if s not in ("create", "apply")
       and not c.startswith(f"cd {_target} &&")], [])

# create 를 건너뛴(기존) 프로젝트에 strip 을 내면 pnpm remove 가 에러를 내며 계획이 죽는다.
with tempfile.TemporaryDirectory() as _existing:
    (Path(_existing) / "package.json").write_text("{}", encoding="utf-8")
    _nest = stacks.plan(stacks.resolve("nest-api"), Path(_existing))
    check("--plan: 비어 있지 않은 대상에는 create·strip 을 내지 않는다",
          [s for s, _ in _nest if s in ("create", "strip")], [])
    try:
        stacks.plan(_web, Path(_existing) / "package.json")
        check("--plan: 파일을 대상으로 주면 거부", "통과했다", "StackError")
    except stacks.StackError as e:
        check("--plan: 파일을 대상으로 주면 거부", "디렉터리가 아니다" in str(e), True)

with tempfile.TemporaryDirectory() as _tmp:
    _proj = Path(_tmp)
    # MCP 정의는 jigkit 안(library/mcp/)에 쓰이는 것이 정상 동작이다. 검사가 저장소를
    # 더럽히면 안 되므로 여기서만 샌드박스로 돌린다.
    stacks.MCP_DIR = _proj / "mcp"
    stacks.MCP_DIR.mkdir()
    (_proj / "pyproject.toml").write_text(
        '[project]\nname = "t"\ndependencies = ["fastapi", "sqlmodel", "logfire"]\n'
        '\n[dependency-groups]\ndev = ["ruff", "pyright", "ty", "pytest", "testcontainers"]\n',
        encoding="utf-8")
    (_proj / "package.json").write_text(
        '{"name":"t","devDependencies":{"@biomejs/biome":"2","vitest":"3","typescript":"5"},'
        '"dependencies":{"zod":"4"}}\n', encoding="utf-8")
    # 의존성이 이미 선언돼 있다 = 설치가 끝난 프로젝트다. 락파일은 그 상태의 일부이고,
    # `pnpm` 항목이 어느 패키지 매니저인지 감지하는 근거다 (package.json 만으로는 모른다).
    (_proj / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")

    check("의존성 파싱: 선언 섹션만 본다 (name 은 의존성이 아니다)",
          "t" in stacks._deps(_proj), False)
    check("의존성 파싱: PEP 508 extras 를 벗긴다", "fastapi" in stacks._deps(_proj), True)

    stack_apply.apply(_api, _proj, write=True)
    _fmt = _proj / ".claude" / "hooks" / "jig-format"
    _settings = json.loads((_proj / ".claude" / "settings.json").read_text(encoding="utf-8"))
    check("배치: PostToolUse 항목 1개", len(_settings["hooks"]["PostToolUse"]), 1)

    _before = _fmt.read_text(encoding="utf-8")
    stack_apply.apply(_api, _proj, write=True)
    check("멱등: 같은 조합을 두 번 적용해도 diff 가 없다",
          _fmt.read_text(encoding="utf-8"), _before)

    # 스택 추가가 앞 스택의 분기를 지우면 훅이 조용히 사라진다 — 실제로 그랬다.
    stack_apply.apply(stacks.resolve("typescript"), _proj, write=True)
    _merged = _fmt.read_text(encoding="utf-8")
    check("병합: typescript 추가 후에도 python 분기가 남는다", "# ruff" in _merged, True)
    check("병합: typescript 분기도 들어간다", "# biome" in _merged, True)
    check("병합: 항목은 여전히 1개",
          len(json.loads((_proj / ".claude" / "settings.json")
                         .read_text(encoding="utf-8"))["hooks"]["PostToolUse"]), 1)

    # 마커 밖의 사람 손 편집은 살아남아야 한다.
    _fmt.write_text(_merged.replace("import json", "import json  # 사람이 쓴 주석"),
                    encoding="utf-8")
    stack_apply.apply(_api, _proj, write=True)
    check("보존: 마커 밖 편집이 남는다",
          "# 사람이 쓴 주석" in _fmt.read_text(encoding="utf-8"), True)

    check("check: 배치 후에는 빈 목록",
          [i for i, _ in stacks.check(stacks.resolve("typescript"), _proj)], [])

    # MCP 정의는 카탈로그 한 곳에만 산다. apply 가 사본을 깔면 그 사본이 빌드에서
    # 카탈로그를 **이기므로**, 이후의 카탈로그 수정이 조용히 무시된다.
    check("MCP: apply 는 library/mcp/ 에 사본을 만들지 않는다",
          sorted(p.name for p in stacks.MCP_DIR.glob("*.json")), [])

    # 사람이 override 를 두는 것은 정상이다. 다만 **카탈로그와 다른 사본이 이기고 있다**는
    # 사실은 보여야 한다 — 안 보이면 카탈로그를 고쳐도 세션이 안 바뀌는데 아무 신호가 없다.
    # mcp 항목이 있는 조합을 쓴다. 언어 base 만으로는 mcp 표면이 없을 수 있고,
    # 그때 next() 가 StopIteration 으로 터지면 검사가 아니라 사고다.
    _ts = stacks.resolve("web-app")
    _mcp_ids = [i["id"] for i in _ts["items"] if i["surface"] == "mcp"]
    check("MCP: 검사용 조합에 mcp 항목이 있다", bool(_mcp_ids), True)
    _mcp_id = _mcp_ids[0]
    (stacks.MCP_DIR / f"{_mcp_id}.json").write_text(
        '{"command": "echo", "args": ["override"]}\n', encoding="utf-8")
    check("MCP: 카탈로그와 다른 override 를 check 가 짚는다",
          [i for i, _ in stacks.check(_ts, _proj) if i == _mcp_id], [_mcp_id])
    check("MCP: apply 도 같은 것을 짚는다",
          any("카탈로그와 다르다" in l for l in stack_apply.apply(_ts, _proj, write=False)), True)

    # 같은 내용이면 override 가 아니다 — 조용해야 한다. 여기가 시끄러우면 사람이 무시한다.
    (stacks.MCP_DIR / f"{_mcp_id}.json").write_text(
        json.dumps(next(i for i in _ts["items"] if i["id"] == _mcp_id)["mcp"]) + "\n",
        encoding="utf-8")
    check("MCP: 내용이 같은 사본은 짚지 않는다",
          [i for i, _ in stacks.check(_ts, _proj) if i == _mcp_id], [])
    (stacks.MCP_DIR / f"{_mcp_id}.json").unlink()

    # 훅·게이트는 걸렸는데 도구가 안 깔린 상태를 "ok" 라고 하면 안 된다 — 표면 검사와
    # detect 를 **둘 다** 본다. 매 편집마다 stderr 만 나오는 형태가 여기서 새어 나갔다.
    with tempfile.TemporaryDirectory() as _bare:
        _b = Path(_bare)
        (_b / "pyproject.toml").write_text('[project]\nname = "t"\n', encoding="utf-8")
        stack_apply.apply(_api, _b, write=True)
        check("check: 훅은 걸렸지만 도구가 안 깔리면 잡는다",
              {i for i, _ in stacks.check(_api, _b)} >= {"ruff", "pyright"}, True)
        # check 를 따로 부르지 않는 사람에게도 apply 가 그 자리에서 말해야 한다.
        check("undetected: 안 깔린 도구를 배치 직후에 짚는다",
              set(stacks.undetected(_api, _b)) >= {"ruff", "pyright"}, True)
        check("undetected: 표면 배치와 무관하다 (배치해도 남는다)",
              "ruff" in stacks.undetected(_api, _b), True)

    check("undetected: 도구가 다 깔린 프로젝트에서는 빈 목록",
          stacks.undetected(_api, _proj), [])
    check("undetected: 없는 프로젝트에는 아무 말도 하지 않는다",
          stacks.undetected(_api, _proj / "없다"), [])

    # 스킬이 이 줄을 그대로 실행한다 — 공백이 든 경로가 감싸여야 한다.
    _spaced = stacks.plan(_api, Path("/tmp/jig selftest/api"))
    check("--plan: 공백이 든 경로를 감싼다",
          all("'/tmp/jig selftest/api'" in c for s, c in _spaced if s != "apply"), True)

    # 형태가 이상한 남의 settings.json 에 트레이스백을 내지 않는다.
    (_proj / ".claude" / "settings.json").write_text('{"hooks": null}', encoding="utf-8")
    stack_apply.apply(_api, _proj, write=True)
    check("배치: hooks 가 null 이어도 진단으로 처리한다",
          isinstance(json.loads((_proj / ".claude" / "settings.json")
                                .read_text(encoding="utf-8"))["hooks"], dict), True)

    _fmt.write_text(_merged.replace("# ruff", "# gone"), encoding="utf-8")
    check("check: 분기를 지우면 그 항목이 나온다",
          [i for i, _ in stacks.check(_api, _proj) if i == "ruff"], ["ruff"])

    # 사람이 주석 처리한 분기를 "있다" 고 세면 체크가 조용히 거짓말한다.
    _fmt.write_text("\n".join(
        ("    # " + l.strip()) if "# ruff" in l else l
        for l in _merged.splitlines()), encoding="utf-8")
    check("check: 주석 처리된 분기는 없는 것으로 본다",
          [i for i, _ in stacks.check(_api, _proj) if i == "ruff"], ["ruff"])
    _fmt.write_text(_merged, encoding="utf-8")

    # 카탈로그에서 은퇴한 항목의 분기는 남아서 계속 돌면 안 된다.
    _fmt.write_text(_merged.replace(
        "# ruff", "# ruff\n    (['.zz'], 'echo zz'),  # zzz-retired"), encoding="utf-8")
    check("check: 카탈로그에 없는 분기를 남는 것으로 보고한다",
          [i for i, _ in stacks.check(_api, _proj) if i == "zzz-retired"], ["zzz-retired"])
    _out = stack_apply.apply(_api, _proj, write=True)
    check("apply: 은퇴 분기를 지우고 무엇을 지웠는지 말한다",
          any("zzz-retired" in l and "은퇴" in l for l in _out), True)
    check("apply: 은퇴 뒤 파일에서 사라진다",
          "zzz-retired" in _fmt.read_text(encoding="utf-8"), False)
    check("은퇴가 다른 스택 분기를 데려가지 않는다 — biome 은 남는다",
          "# biome" in _fmt.read_text(encoding="utf-8"), True)

    # 유지되는 분기는 그 줄을 그대로 두지 않고 카탈로그 정의로 다시 렌더한다 — 그래야
    # 다른 스택만 apply 한 프로젝트에 옛 명령이 남지 않는다.
    _fmt.write_text(_fmt.read_text(encoding="utf-8")
                    .replace("pnpm biome check --write", "옛-명령"), encoding="utf-8")
    stack_apply.apply(_api, _proj, write=True)
    check("유지 분기가 카탈로그 정의로 갱신된다",
          "옛-명령" in _fmt.read_text(encoding="utf-8"), False)

    # 사람이 같은 항목에 넣어 둔 다른 훅을 지우면 안 된다.
    _spath = _proj / ".claude" / "settings.json"
    _s = json.loads(_spath.read_text(encoding="utf-8"))
    _s["hooks"]["PostToolUse"][0]["hooks"].append(
        {"type": "command", "command": "./my-own-notify.sh"})
    _spath.write_text(json.dumps(_s), encoding="utf-8")
    stack_apply.apply(_api, _proj, write=True)
    _after = json.loads(_spath.read_text(encoding="utf-8"))["hooks"]["PostToolUse"][0]["hooks"]
    check("배치: 같은 항목의 남의 훅이 살아남는다",
          any("my-own-notify" in (h.get("command") or "") for h in _after), True)
    check("배치: 우리 훅도 그대로 하나",
          sum("jig-format" in (h.get("command") or "") for h in _after), 1)

    (_proj / "package.json").write_text(
        '{"name":"t","devDependencies":{"@biomejs/biome":"2","prettier":"3"}}\n',
        encoding="utf-8")
    check("check: 충돌하는 도구가 남아 있으면 나온다",
          [i for i, _ in stacks.check(stacks.resolve("typescript"), _proj) if i == "prettier"],
          ["prettier"])

    # 우리 마커가 없는 파일은 덮지 않는다.
    _fmt.write_text("#!/bin/sh\n사람이 쓴 훅\n", encoding="utf-8")
    try:
        stack_apply.apply(_api, _proj, write=False)
        check("남의 파일 -> 거부", "통과했다", "StackError")
    except stacks.StackError as e:
        check("남의 파일 -> 거부", "생성 마커가 없다" in str(e), True)

# ---------------------------------------------------------------- 프로젝트 지침 편입
#
# 프로필 세션은 `--setting-sources user` 로 뜨고, 그 플래그가 프로젝트 `CLAUDE.md`
# 자동 발견까지 함께 끈다 [M: probe/results/memory-files.md]. 그래서 컴파일러가 내용을
# 시스템 프롬프트로 편입한다. **golden 은 이 분기를 지나가지 않는다** — 골든 프로젝트는
# `/__golden__` 이라 `CLAUDE.md` 가 없기 때문이다. 빠지면 조용히 빠진다.

import build  # noqa: E402

_dev = build.load_profile("developer")

with tempfile.TemporaryDirectory() as _d:
    _p = Path(_d)
    check("CLAUDE.md 없음 -> 편입 없음", build.project_memory(_p), None)

    (_p / "CLAUDE.md").write_text("   \n\n", encoding="utf-8")
    check("빈 CLAUDE.md -> 편입 없음", build.project_memory(_p), None)

    (_p / "CLAUDE.md").write_text("# 프로젝트 규칙\n\n마커 PROJ_MEM_TEST 를 지킨다.\n",
                                  encoding="utf-8")
    _sp = build.build_system_prompt(_dev, _p)
    check("CLAUDE.md -> 시스템 프롬프트에 들어온다", "마커 PROJ_MEM_TEST 를 지킨다." in _sp, True)

    # 강제되는 스코프(완료 정의·입출력)가 뒤에 남아야 한다 — 순서는 조용히 뒤집힌다.
    # `find` 로 위치를 먼저 뽑는다: 마커가 빠지는 회귀에서 `index` 는 ValueError 로 터져
    # **뒤의 검사와 결과 요약이 통째로 안 돈다** — 게이트가 조용해지는 그 모양이다.
    _i = _sp.find("PROJ_MEM_TEST")
    check("순서: 프로젝트 지침 < 완료 정의 · 입출력",
          [s for s in ("# 완료 정의", "# 이 단계의 입출력")
           if s in _sp and _sp.index(s) < _i], [])
    check("순서: 하네스 공통 지침이 맨 앞", _sp.find("# 하네스 공통 지침"), 0)

    # CLI 가 발견하는 범위를 그대로 덮어야 한다 [M: probe/results/memory-files.md].
    # 좁으면 "적어 뒀는데 안 실린" 상태가 소리 없이 생긴다.
    (_p / "CLAUDE.local.md").write_text("로컬 마커 LOCAL_MEM_TEST.\n", encoding="utf-8")
    (_p / "imported.md").write_text("가져온 마커 IMPORTED_MEM_TEST.\n", encoding="utf-8")
    (_p / "CLAUDE.md").write_text(
        "마커 PROJ_MEM_TEST 를 지킨다.\n\n@imported.md\n\n@없는파일.md 는 그대로 둔다.\n",
        encoding="utf-8")
    _mem = build.project_memory(_p)
    check("CLAUDE.local.md 도 편입된다", "LOCAL_MEM_TEST" in _mem, True)
    check("@경로 import 가 펴진다", "IMPORTED_MEM_TEST" in _mem, True)
    check("풀리지 않는 @ 는 건드리지 않는다", "@없는파일.md" in _mem, True)

    # 산문 안에서는 `@경로` 뒤에 문장부호가 붙는다. 마침표까지 경로로 잡으면 조용히 안 펴진다.
    (_p / "CLAUDE.md").write_text("자세한 것은 @imported.md. 끝.\n", encoding="utf-8")
    _mem = build.project_memory(_p)
    check("문장 끝 마침표가 붙어도 펴진다", "IMPORTED_MEM_TEST" in _mem, True)
    check("벗겨 낸 마침표는 돌려준다", "IMPORTED_MEM_TEST." in _mem, True)

    # 순환 참조. 깊이 상한만으로는 같은 본문이 5번 복제된다.
    (_p / "a.md").write_text("본문 CYCLE_MEM_TEST.\n\n@b.md\n", encoding="utf-8")
    (_p / "b.md").write_text("@a.md\n", encoding="utf-8")
    (_p / "CLAUDE.md").write_text("@a.md\n", encoding="utf-8")
    check("순환 import -> 본문은 한 번만", build.project_memory(_p).count("CYCLE_MEM_TEST"), 1)

    # UTF-8 이 아닌 파일 하나로 기동 전체가 죽으면 안 된다 — 편입은 부가, 기동이 본체다.
    # 못 읽은 것만 빠지고 나머지는 남아야 한다 (stderr 경고는 눈으로 확인).
    (_p / "CLAUDE.md").write_bytes("마커 CP949_MEM_TEST".encode("cp949"))
    _mem = build.project_memory(_p)
    check("디코딩 실패 -> 예외가 아니라 제외", "CP949_MEM_TEST" in _mem, False)
    check("디코딩 실패해도 나머지는 남는다", "LOCAL_MEM_TEST" in _mem, True)

check("골든 프로젝트에는 편입할 것이 없다 (golden 이 머신 독립을 유지한다)",
      build.project_memory(Path("/__golden__")), None)

# bootstrap 이 `~/.claude/CLAUDE.md` 로 까는 기본 지침. 파일명을 바꾸면 bootstrap 은
# **다음 새 머신 세팅 도중에야** 터진다 — 고치기 가장 나쁜 순간이다.
_bootstrap = (ROOT / "bootstrap.sh").read_text(encoding="utf-8")
check("bootstrap 이 참조하는 전역 지침 파일이 실재한다",
      (ROOT / "core" / "GLOBAL_CLAUDE.md").is_file(), True)
check("bootstrap 이 그 파일을 `jig lang` 으로 깐다", '"$JIG" lang' in _bootstrap, True)

# 문자열 매칭만으로는 부족했다 — bootstrap 이 부르는 형태가 **설치를 하지 않는** 경로였는데
# `'"$JIG" lang' in _bootstrap` 은 초록불이었다. 그래서 bootstrap 이 실제로 넘기는 인자로
# 돌려 **파일이 생기는지** 본다. 설치 대상만 임시 경로로 바꿔치기한다.
_real_dst = cli.GLOBAL_DST
with tempfile.TemporaryDirectory() as _d:
    cli.GLOBAL_DST = Path(_d) / ".claude" / "CLAUDE.md"
    try:
        _argv = re.search(r'"\$JIG" lang "\$@"', _bootstrap)
        check("bootstrap 이 인자를 그대로 넘긴다", bool(_argv), True)
        check("bootstrap 의 기본 인자가 --install 이다", "--install" in _bootstrap, True)

        cli.cmd_lang([])                       # 조회는 아무것도 쓰지 않는다
        check("jig lang (무인자) -> 쓰지 않는다", cli.GLOBAL_DST.exists(), False)

        cli.cmd_lang(["--install"])            # bootstrap 의 기본 경로
        check("jig lang --install -> 깔린다", cli.GLOBAL_DST.is_file(), True)
        check("깔린 내용이 템플릿과 같다",
              cli.GLOBAL_DST.read_text(encoding="utf-8"),
              (ROOT / "core" / "GLOBAL_CLAUDE.md").read_text(encoding="utf-8"))

        # 사람이 쓴 파일을 덮기 전에 **한 번은** 남긴다. tar 백업은 reset 경로에만 있다.
        cli.GLOBAL_DST.write_text("사람이 쓴 전역 지침 HANDWRITTEN\n", encoding="utf-8")
        cli.cmd_lang(["--install"])
        _bak = cli.GLOBAL_DST.with_suffix(".md.jigkit-backup")
        check("덮기 전에 백업이 남는다", "HANDWRITTEN" in _bak.read_text(encoding="utf-8"), True)
        cli.cmd_lang(["--install"])
        check("백업은 갱신하지 않는다 (사람이 쓴 것이 지켜져야 한다)",
              "HANDWRITTEN" in _bak.read_text(encoding="utf-8"), True)
    finally:
        cli.GLOBAL_DST = _real_dst

# `jig lang` 은 그 파일의 마커 블록만 갈아 끼운다. 마커가 없어지면 LookupError 인데,
# 그 시점은 사람이 언어를 바꾸려는 순간이다 — 여기서 미리 잡는다.
import mdblock  # noqa: E402

_global = (ROOT / "core" / "GLOBAL_CLAUDE.md").read_text(encoding="utf-8")
check("전역 지침에 언어 마커가 산다",
      [m for m in cli.LANG_MARKERS if m not in _global.splitlines()], [])
check("현재 언어를 블록에서 되읽는다", bool(cli.current_lang()), True)

_swapped = mdblock.splice(_global, *cli.LANG_MARKERS, cli._lang_body("English"))
check("언어 교체 -> 새 언어가 들어온다",
      "Respond in English for every command" in _swapped, True)
check("언어 교체 -> 나머지 지침은 그대로",
      _swapped.count("Karpathy"), _global.count("Karpathy"))

# ---------------------------------------------------------------- 결과

if _failures:
    print(f"FAIL {len(_failures)}건\n")
    for f in _failures:
        print(f"  {f}\n")
    raise SystemExit(1)
print("ok   커밋 게이트 · 기동 게이트 · 문서 라우팅 · 생성물 검사 통과")
