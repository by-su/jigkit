#!/usr/bin/env python3
"""jig 명령 구현. bin/jig 는 여기로 넘기기만 한다."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from build import BUILD, BuildError, HARNESS, compile_profile, discover, launch_argv, load_profile, write_readback


def die(msg: str) -> None:
    print(f"jig: {msg}", file=sys.stderr)
    raise SystemExit(1)


def record_state(name: str, project: Path) -> list[str]:
    """세션 불변 기동: 상태 기록 -> 되읽기 -> 선행 산출물 확인."""
    state = {"profile": name, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    prev = project / ".harness" / "state.json"
    if prev.is_file():
        try:
            state["previous"] = json.loads(prev.read_text(encoding="utf-8")).get("profile")
        except (json.JSONDecodeError, OSError):
            pass
    write_readback(prev, json.dumps(state, indent=2, ensure_ascii=False) + "\n")

    missing = []
    for pattern in load_profile(name).get("inputs") or []:
        d = project / Path(pattern).parent
        if not d.is_dir() or not any(d.iterdir()):
            missing.append(str(Path(pattern).parent))
    return missing


def _one_run(argv: list[str], cwd: Path) -> int:
    proc = subprocess.run(
        argv + ["--output-format", "json", "-p", "hi"],
        cwd=cwd, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        die(f"측정 실패 (rc={proc.returncode}): {proc.stderr.strip()[:300]}")
    u = json.loads(proc.stdout).get("usage", {})
    return sum(u.get(k) or 0 for k in
               ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))


def measure(argv: list[str], cwd: Path, runs: int = 2) -> int:
    """기동 토큰을 실측한다. 모델을 호출하므로 쿼터를 쓴다.

    [M] 콜드 캐시 런은 같은 설정에서 93,118 을, 웜 런은 14,193 을 보고했다.
    합산값은 캐시 상태에 크게 흔들린다 → 여러 번 돌려 **최솟값**을 쓴다.
    최솟값이 곧 "이 설정이 실제로 지는 컨텍스트"에 가장 가깝다.
    """
    return min(_one_run(argv, cwd) for _ in range(runs))


def cmd_run(name: str, project: Path, extra: list[str]) -> None:
    argv = launch_argv(name, project)
    missing = record_state(name, project)
    p = load_profile(name)

    print(f"[{name}] {p.get('title', '')} — {p.get('summary', '')}", file=sys.stderr)
    if missing:
        print(f"  ⚠ 선행 산출물 없음: {', '.join(missing)}", file=sys.stderr)
    print(f"  프로젝트: {project}", file=sys.stderr)

    os.chdir(project)
    os.execvp("claude", argv + extra)


def cmd_list() -> None:
    if not (names := discover()):
        print("프로필이 없다. `jig new <이름>` 으로 만든다.")
        return
    for n in names:
        p = load_profile(n)
        n_sk, n_ag = len(p.get("skills") or []), len(p.get("agents") or [])
        n_mcp = len(p.get("mcp") or [])
        print(f"  {n:<12} {p.get('title', ''):<10} 스킬 {n_sk} · 에이전트 {n_ag} · MCP {n_mcp}"
              f"   {p.get('summary', '')}")


def cmd_build(names: list[str], project: Path) -> None:
    for n in names or discover():
        out = compile_profile(n, project)["out"]
        print(f"built {n:<12} -> {out.relative_to(HARNESS)}")


def cmd_doctor(names: list[str], project: Path) -> None:
    failed = False
    for n in names or discover():
        built = compile_profile(n, project)
        out, p = built["out"], built["profile"]
        settings = json.loads((out / "settings.json").read_text(encoding="utf-8"))
        deny = settings.get("permissions", {}).get("deny", [])
        n_sk = len(list((out / "skills").iterdir())) if (out / "skills").is_dir() else 0
        approx = len((out / "system-prompt.md").read_text(encoding="utf-8")) // 4

        print(f"ok   {n:<12} 프롬프트 ~{approx}토큰 · 스킬 {n_sk} · deny {len(deny)}건")

        # [M] Write(...) 규칙은 차단되지 않는다. 조용히 틀리는 실패 모드라 여기서 잡는다.
        for rule in deny:
            if rule.startswith("Write("):
                print(f"     FAIL {n}: Write(...) 는 차단되지 않는다. Edit(...) 로 바꿔라 — {rule}")
                failed = True
        if p.get("mcp") and not (out / "mcp.json").is_file():
            print(f"     FAIL {n}: mcp 를 선언했는데 mcp.json 이 없다")
            failed = True

    failed |= _check_handoff_graph(names or discover())
    raise SystemExit(1 if failed else 0)


def _check_handoff_graph(names: list[str]) -> bool:
    """핸드오프 사슬이 끊겼는지 본다.

    프로필이 늘어날수록 조용히 깨지는 곳이다 — 어떤 단계가 아무도 만들지 않는 문서를
    기다리거나, 아무도 안 읽는 문서를 만들면 파이프라인이 거기서 멈춘다.
    """
    produced: dict[str, str] = {}
    consumed: dict[str, list[str]] = {}
    for n in names:
        p = load_profile(n)
        for o in p.get("outputs") or []:
            produced.setdefault(o, n)
        for i in (p.get("inputs") or []) + (p.get("inputs_optional") or []):
            consumed.setdefault(i, []).append(n)

    failed = False
    for path, readers in sorted(consumed.items()):
        if path not in produced:
            print(f"     FAIL 핸드오프: {readers} 가 `{path}` 를 읽는데 아무 프로필도 만들지 않는다")
            failed = True
    for path, writer in sorted(produced.items()):
        # 소스 코드처럼 다음 단계가 문서로 읽지 않는 산출물은 검사 대상이 아니다.
        if path.startswith("docs/") and path not in consumed:
            print(f"     warn 핸드오프: {writer} 가 `{path}` 를 만드는데 아무도 읽지 않는다")
    return failed


def cmd_budget(names: list[str], project: Path) -> None:
    """프로필별 기동 토큰을 실측하고 상한과 대조한다."""
    failed = False
    for n in names or discover():
        p = load_profile(n)
        total = measure(launch_argv(n, project), project)
        limit = p.get("budget_tokens")
        if limit is None:
            print(f"     {n:<12} {total:>7,} 토큰  (상한 미설정)")
            continue
        ok = total <= limit
        failed |= not ok
        print(f"{'ok  ' if ok else 'FAIL'} {n:<12} {total:>7,} 토큰  (상한 {limit:,})")
    raise SystemExit(1 if failed else 0)


def cmd_growth(counts: list[int], project: Path) -> None:
    """스킬 개수 대비 기동 토큰을 실측한다.

    이 하네스의 존재 이유가 "스킬이 늘어도 세션은 평평하다" 이므로,
    그 주장의 기울기를 추정이 아니라 측정으로 갖고 있어야 한다.
    [M:CC-SKILL-DESC-COST]
    """
    root = HARNESS / "build" / "_growth"
    if root.exists():
        import shutil
        shutil.rmtree(root)

    print(f"{'스킬':>5}  {'기동 토큰':>10}  {'증가':>8}  {'스킬당':>7}")
    base = None
    for n in counts:
        d = root / f"n{n}"
        (d / ".claude-plugin").mkdir(parents=True)
        (d / ".claude-plugin" / "plugin.json").write_text(json.dumps(
            {"name": f"growth{n}", "version": "0.0.1",
             "description": "budget growth probe", "author": {"name": "arto"}}), encoding="utf-8")
        for i in range(n):
            sd = d / "skills" / f"probe-skill-{i:03d}"
            sd.mkdir(parents=True)
            # 설명 길이가 비용을 좌우하므로 실제 스킬과 비슷한 길이로 맞춘다.
            (sd / "SKILL.md").write_text(
                f"---\nname: probe-skill-{i:03d}\n"
                f"description: Synthetic probe skill number {i:03d}. Used only to measure how much "
                f"always-on context a single skill description costs at session start. "
                f"Never invoke this skill; it does nothing useful.\n---\n\nNo-op.\n",
                encoding="utf-8")

        argv = ["claude", "--plugin-dir", str(d),
                "--settings", json.dumps({"disableBundledSkills": True}),
                "--setting-sources", "user",
                "--mcp-config", json.dumps({"mcpServers": {}}), "--strict-mcp-config"]
        total = measure(argv, project)
        if base is None:
            base, delta, per = total, 0, 0.0
        else:
            delta = total - base
            per = delta / n if n else 0.0
        print(f"{n:>5}  {total:>10,}  {delta:>+8,}  {per:>7.0f}")


def cmd_golden(names: list[str], project: Path, update: bool) -> None:
    """컴파일러 회귀 검사. build/ 는 커밋하지 않고 기대 출력만 커밋한다.

    settings.json 의 deny 규칙에 프로젝트 절대경로가 박히므로,
    golden 비교는 **고정된 가짜 프로젝트 경로**로 컴파일해 머신 독립적으로 만든다.
    """
    import filecmp
    project = Path("/__golden__")
    golden = HARNESS / "tests" / "golden" / "claude"
    failed = False
    for n in names or discover():
        out = compile_profile(n, project)["out"]
        exp = golden / n
        if update:
            import shutil
            if exp.exists():
                shutil.rmtree(exp)
            shutil.copytree(out, exp)
            print(f"updated golden/{n}")
            continue
        if not exp.is_dir():
            print(f"FAIL {n}: golden 이 없다. `jig golden --update {n}`")
            failed = True
            continue
        cmp = filecmp.dircmp(out, exp)
        diffs = _walk_diff(cmp)
        if diffs:
            failed = True
            print(f"FAIL {n}: 컴파일 출력이 golden 과 다르다 — {', '.join(diffs)}")
        else:
            print(f"ok   {n}")
    raise SystemExit(1 if failed else 0)


def _walk_diff(cmp) -> list[str]:
    out = list(cmp.diff_files) + list(cmp.left_only) + list(cmp.right_only) + list(cmp.funny_files)
    for sub in cmp.subdirs.values():
        out += _walk_diff(sub)
    return out


def main() -> None:
    args = sys.argv[1:]
    if not args:
        die("사용법: jig <프로필> [프로젝트] | list | build | doctor | budget | golden | argv")
    cmd, rest = args[0], args[1:]
    project = Path(os.environ.get("HNS_PROJECT") or os.getcwd()).resolve()

    try:
        if cmd == "list":
            cmd_list()
        elif cmd == "build":
            cmd_build(rest, project)
        elif cmd == "doctor":
            cmd_doctor(rest, project)
        elif cmd == "budget":
            cmd_budget(rest, project)
        elif cmd == "growth":
            counts = [int(x) for x in rest] or [0, 10, 25, 50]
            cmd_growth(counts, project)
        elif cmd == "golden":
            update = "--update" in rest
            cmd_golden([r for r in rest if not r.startswith("-")], project, update)
        elif cmd == "argv":
            if not rest:
                die("jig argv <프로필>")
            print(" ".join(shlex.quote(a) for a in launch_argv(rest[0], project)))
        else:
            if rest and Path(rest[0]).is_dir():
                project, rest = Path(rest[0]).resolve(), rest[1:]
            cmd_run(cmd, project, rest)
    except BuildError as e:
        die(str(e))


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    main()
