#!/usr/bin/env python3
"""커밋 게이트와 문서 라우팅의 단위 검사.

**false negative 가 이 장치의 진짜 위험이다.** 게이트가 안 뜨면 아무 일도 안 일어난
것처럼 보이고, 그래서 조용히 무력화된 상태를 아무도 눈치채지 못한다. golden 은
컴파일러만 보고 probe 는 "가능한가" 만 증명한다 — 회귀를 잡는 건 여기다.

의존성 없이 돈다: `python3 tests/test_gate.py` 또는 `jig selftest`.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "adapters"))

import commands  # noqa: E402
import touched  # noqa: E402


def _load_gate():
    """`bin/jig-commit-gate` 는 확장자가 없어 로더를 직접 지정해야 한다."""
    loader = importlib.machinery.SourceFileLoader(
        "gate", str(ROOT / "bin" / "jig-commit-gate"))
    spec = importlib.util.spec_from_loader("gate", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)      # __name__ 이 "gate" 라 main() 은 돌지 않는다
    return mod


gate = _load_gate()

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

# ---------------------------------------------------------------- 실제 사건 회귀

# 이 도구가 존재하는 이유. 전역 전환 커밋(00b089f)에서 `jig usage` 를 문서화한 줄을
# 놓쳤다. **줄 번호로 단언하지 않는다** — 문서가 자라면 번호는 밀린다(실제로 밀렸다).
# 변하지 않는 것은 "그 개념을 설명하는 줄을 짚는가" 다.
text, has_primary = touched.report("00b089f~1..00b089f")
check("놓쳤던 커밋에서 primary 히트가 난다", has_primary, True)
usage_lines = [l for l in text.splitlines() if "jig usage" in l]
check("jig usage 를 문서화한 줄을 짚는다", len(usage_lines) >= 2, True)
for doc in ["README.md:", "README.ko.md:"]:
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

# ---------------------------------------------------------------- 결과

if _failures:
    print(f"FAIL {len(_failures)}건\n")
    for f in _failures:
        print(f"  {f}\n")
    raise SystemExit(1)
print("ok   커밋 게이트 · 문서 라우팅 검사 통과")
