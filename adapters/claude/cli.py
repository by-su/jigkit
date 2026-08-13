#!/usr/bin/env python3
"""jig 명령 구현. bin/jig 는 여기로 넘기기만 한다."""
from __future__ import annotations

import fnmatch
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# sources 는 도구 중립이라 adapters/ 바로 아래 산다. build.py 도 같은 처리를 한다.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import commands  # noqa: E402
import launchgate  # noqa: E402
import sources  # noqa: E402
import touched  # noqa: E402
from build import BUILD, BuildError, HARNESS, compile_profile, discover, discover_fixtures, launch_argv, load_profile, write_readback  # noqa: E402
from sources import SourceError  # noqa: E402


def die(msg: str) -> None:
    print(f"jig: {msg}", file=sys.stderr)
    raise SystemExit(1)


def record_state(name: str, project: Path, prev: dict | None) -> list[str]:
    """세션 불변 기동: 상태 기록 -> 되읽기 -> 선행 산출물 확인.

    prev 는 호출자가 **기동 게이트 판정에 쓴 것과 같은** 파싱 결과다. 여기서 파일을
    다시 읽으면 게이트 입력과 기록 입력이 갈라질 수 있고, "게이트가 덮어쓰기보다
    먼저" 라는 순서도 주석이 아니라 호출 서명이 지킨다.
    """
    state = {"profile": name, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if isinstance(prev, dict):
        state["previous"] = prev.get("profile")
        # 판정 기록(done·next·주인)은 /profile 이 새 판정을 쓸 때까지 **모든 기동**
        # 에서 한 단위로 이월한다. 기동은 판정을 소비하지 않는다 — 같은 프로필
        # 재기동(복구)이 지우면 복구 "시작"이 곧 통과가 되고, 옆길 기동이 지우면
        # 그 다음의 진짜 전진이 무사통과한다 (둘 다 리뷰에서 실측된 구멍).
        # `judged` 는 판정의 주인 — 이월하면서 profile 이 바뀌어도 귀속이 남는다.
        if isinstance(prev.get("done"), dict):
            state["done"] = prev["done"]
            if isinstance(prev.get("next"), str) and prev.get("next"):
                state["next"] = prev["next"]
            judged = prev.get("judged") if isinstance(prev.get("judged"), str) else None
            judged = judged or prev.get("profile")
            if isinstance(judged, str) and judged:
                state["judged"] = judged
    path = project / ".harness" / "state.json"
    write_readback(path, json.dumps(state, indent=2, ensure_ascii=False) + "\n")

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
    # `_` 접두사는 프로필이 아니다 (템플릿·픽스처). discover() 는 이미 그렇게 보는데
    # 기동 경로만 그 규칙을 안 봐서, 이름이 맞는 픽스처는 그대로 세션이 떴다.
    # `_template` 은 name 불일치로 **우연히** 막혀 있었을 뿐이다.
    if name.startswith("_"):
        die(f"'{name}' 은 프로필이 아니다 (템플릿·픽스처). `jig list` 로 확인.")
    # 이름 검증이 게이트보다 먼저다 — 오타 난 프로필에 차단 메시지가 뜨면
    # 존재하지도 않는 프로필의 우회(JIG_GATE_BYPASS)를 코칭하게 된다.
    known = set(discover())
    if name not in known:
        die(f"'{name}' 프로필이 없다. `jig list` 로 확인.")

    # 기동 게이트: /profile 이 남긴 done_when 미충족 기록이 있으면 전진을 막는다.
    # record_state() 가 state.json 을 덮어쓰므로 반드시 그 전에 읽는다.
    try:
        state = json.loads((project / ".harness" / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # 기록 부재·파싱 실패·인코딩 깨짐은 통과 — 게이트는 기록된 미충족에만 반응한다.
        # ValueError 가 JSONDecodeError 와 UnicodeDecodeError 를 함께 덮는다.
        state = None
    kind, msg = launchgate.verdict(state, name, os.environ, known=known)
    if kind == "block":
        die(msg)
    if kind == "bypass":
        print(f"  {msg}", file=sys.stderr)

    argv = launch_argv(name, project)
    missing = record_state(name, project, state)
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
        try:
            # 글롭이 들어가면 선언 줄 수와 실제 스킬 수가 다르다. 편 뒤에 센다.
            n_sk = str(len(sources.resolve(p.get("skills"))))
        except SourceError:
            n_sk = "?"  # 캐시 미동기화. jig doctor 가 이유를 말한다.
        n_ag, n_mcp = len(p.get("agents") or []), len(p.get("mcp") or [])
        print(f"  {n:<12} {p.get('title', ''):<10} 스킬 {n_sk} · 에이전트 {n_ag} · MCP {n_mcp}"
              f"   {p.get('summary', '')}")


def cmd_build(names: list[str], project: Path) -> None:
    for n in names or discover():
        out = compile_profile(n, project)["out"]
        print(f"built {n:<12} -> {out.relative_to(HARNESS)}")


def _flag_value(args: list[str], flag: str) -> str | None:
    if flag not in args:
        return None
    i = args.index(flag)
    if i + 1 >= len(args):
        die(f"{flag} 뒤에 값이 필요하다")
    return args[i + 1]


def cmd_source(rest: list[str]) -> None:
    sub, args = (rest[0] if rest else "list"), rest[1:]

    if sub == "list":
        srcs = sources.load_sources()
        if not srcs:
            print("등록된 소스가 없다. `jig source add <url>` 로 등록한다.")
            return
        for ns, s in sorted(srcs.items()):
            cached = sources.cached_sha(ns)
            ref = str(s.get("ref") or "")
            if cached is None:
                state = "캐시 없음 — jig sync"
            elif cached != ref:
                state = f"캐시가 {cached[:7]} 로 어긋남 — jig sync"
            else:
                state = "동기화됨"
            print(f"  {ns:<14} {ref[:7]}  {s.get('repo', '')}")
            print(f"  {'':<14} {state}")

    elif sub == "add":
        if not args or args[0].startswith("-"):
            die("jig source add <url> [--as <이름>]")
        ns, sha = sources.add_source(args[0], _flag_value(args, "--as"))
        print(f"등록했다: {ns}  {args[0]} @ {sha[:7]}")
        print(f"  `jig sync {ns}` 로 받는다.")

    else:
        die(f"jig source <list|add> — 받은 것: {sub}")


def _declarers(skill_id: str) -> list[str]:
    """이 스킬을 **이름으로** 선언한 프로필. 글롭은 조용히 빠지므로 세지 않는다."""
    return [n for n in discover() if skill_id in (load_profile(n).get("skills") or [])]


def cmd_sync(rest: list[str]) -> None:
    check, update = "--check" in rest, "--update" in rest
    names = [r for r in rest if not r.startswith("-")]
    srcs = sources.load_sources()
    if not srcs:
        die("등록된 소스가 없다. `jig source add <url>` 로 등록한다.")

    targets = names or sorted(srcs)
    if unknown := [n for n in targets if n not in srcs]:
        die(f"등록되지 않은 소스: {', '.join(unknown)}. `jig source list` 로 확인.")

    if check:
        # ls-remote 한 번씩. 데이터 전송이 없고 캐시도 sources.yaml 도 건드리지 않는다.
        stale = []
        for ns in targets:
            cur, latest = str(srcs[ns].get("ref") or ""), sources.ls_remote(srcs[ns]["repo"])
            if latest == cur:
                print(f"  {ns:<14} {cur[:7]}              최신")
            else:
                stale.append(ns)
                print(f"  {ns:<14} {cur[:7]} -> {latest[:7]}   업데이트 있음")
        if stale:
            print(f"\n적용: jig sync --update {' '.join(stale)}")
        return

    for ns in targets:
        if update:
            _sync_update(ns, srcs)
        else:
            ref = sources.fetch(ns)
            if srcs[ns].get("ref") != ref:
                srcs[ns]["ref"] = ref
                sources.save_sources(srcs)
            print(f"synced {ns:<14} {ref[:7]}  스킬 {len(sources.discover_skills(ns))}")


def _sync_update(ns: str, srcs: dict) -> None:
    """최신으로 올리고 **무엇이 바뀌었는지** 스킬 단위로 보여준다.

    스킬은 데이터가 아니라 에이전트에게 주는 지시문이다. 상류가 조용히 바뀌면
    에이전트 행동이 리뷰 없이 바뀐다 — 그래서 적용 시점에 diff 를 사람에게 보여준다.
    """
    old = sources.cached_sha(ns) or str(srcs[ns].get("ref") or "") or None
    new = sources.ls_remote(srcs[ns]["repo"])

    if old == new:
        print(f"  {ns:<14} {new[:7]}  이미 최신")
        return

    sources.fetch(ns, new)
    srcs[ns]["ref"] = new
    sources.save_sources(srcs)

    if old is None:
        print(f"  {ns:<14} 새로 받았다 {new[:7]} — 비교할 이전 상태가 없다")
        return

    print(f"\n{ns}  {old[:7]} -> {new[:7]}\n")
    d = sources.compare(ns, old, new)
    delta = 0

    for a in d["added"]:
        delta += a["tokens"]
        print(f"  + {ns}/{a['name']:<24} 새 스킬 (~{a['tokens']}t)")
    for name in d["removed"]:
        who = _declarers(f"{ns}/{name}")
        warn = f"   ⚠ {', '.join(who)} 가 이름으로 선언 중" if who else ""
        print(f"  - {ns}/{name:<24} 삭제됨{warn}")
    for m in d["modified"]:
        if m["desc_changed"]:
            diff = m["new_tokens"] - m["old_tokens"]
            delta += diff
            print(f"  ~ {ns}/{m['name']:<24} 설명 변경  "
                  f"{m['old_tokens']}t -> {m['new_tokens']}t ({diff:+d})")
        else:
            print(f"  ~ {ns}/{m['name']:<24} 본문만 변경")

    if not (d["added"] or d["removed"] or d["modified"]):
        print("  (스킬에는 변화 없음)")
    else:
        print(f"\n  설명 토큰 {delta:+d}. sources.yaml 갱신됨 — `jig doctor` 로 예산을 다시 본다.")


def cmd_skills(rest: list[str]) -> None:
    pattern = next((r for r in rest if not r.startswith("-")), None)
    if not sources.load_sources():
        die("등록된 소스가 없다. `jig source add <url>` 로 등록한다.")

    cat, missing = sources.catalog()
    if missing:
        print(f"⚠ 캐시 없는 소스: {', '.join(missing)} — `jig sync` 를 먼저 실행한다.\n",
              file=sys.stderr)
    if not cat:
        die("스킬이 없다. `jig sync` 를 먼저 실행한다.")

    ids = sorted(cat)
    if pattern:
        glob = pattern if ("*" in pattern or "?" in pattern) else f"*{pattern}*"
        ids = fnmatch.filter(ids, glob)
        if not ids:
            die(f"'{pattern}' 에 맞는 스킬이 없다.")

    srcs = sources.load_sources()
    total = 0
    for ns in sorted({cat[i]["ns"] for i in ids}):
        ref = str(srcs.get(ns, {}).get("ref") or "")
        mine = [i for i in ids if cat[i]["ns"] == ns]
        print(f"\n{ns}  {srcs.get(ns, {}).get('repo', '')} @ {ref[:7]}  ({len(mine)} skills)\n")
        for i in mine:
            s = cat[i]
            total += s["tokens"]
            extras = ",".join(s["extras"])[:20]
            print(f"  {i:<36} ~{s['tokens']:>4}t  {extras:<20}  {s['description'][:60]}")
    print(f"\n합계 {len(ids)} 스킬 · 설명 ~{total:,}토큰 (전부 켤 경우 매 세션 비용)")


def cmd_selftest() -> None:
    """게이트와 라우팅의 단위 검사.

    false negative 가 이 장치의 진짜 위험이다 — 게이트가 안 뜨면 아무 일도 없는 것처럼
    보인다. golden 은 컴파일러만, probe 는 "가능한가" 만 본다. 회귀는 여기서 잡는다.
    """
    proc = subprocess.run([sys.executable, str(HARNESS / "tests" / "test_gate.py")])
    raise SystemExit(proc.returncode)


def cmd_docs(rest: list[str]) -> None:
    """생성된 명령 블록을 갱신하거나(`--update`) 최신인지 검사한다(`--check`).

    이건 라우팅과 달리 **결정 가능**하다 — 재생성 결과가 파일과 같은지 뿐이므로
    실패시켜도 된다.
    """
    write = "--update" in rest
    try:
        stale = commands.apply(write=write)
    except LookupError as e:
        # 마커가 지워졌거나 옮겨졌다. 트레이스백 대신 무엇을 되살려야 하는지 말한다.
        die(str(e))
    if write:
        for t in stale:
            print(f"updated {t}")
        if not stale:
            print("이미 최신이다.")
        return
    if stale:
        for t in stale:
            print(f"FAIL {t}: 명령 블록이 낡았다. `jig docs --update`")
        raise SystemExit(1)
    print("ok   명령 블록이 최신이다 (bin/jig · README.md · README.ko.md)")


def cmd_touched(rest: list[str]) -> None:
    """이 변경이 건드린 개념을 언급하는 문서를 보여준다. **판정하지 않는다.**

    문서가 맞는지는 기계가 알 수 없다. 여기서 없애는 것은 "조용히 안 보고 지나가는 것"
    이지 판단 자체가 아니다. 그래서 실패로 끝나지 않는다.
    """
    rev = next((r for r in rest if not r.startswith("-")), None)
    text, _ = touched.report(rev)
    print(text)


def usage_log_path() -> Path:
    """전역 사용 기록. 정본은 `bin/jig-log-skill` 이 갖고 있고 여기서 같은 규칙을 쓴다.

    훅은 빌드된 플러그인 안에서 독립 실행되므로 이 모듈을 임포트할 수 없다. 그래서
    이 네 줄만 양쪽에 산다.
    """
    if env := os.environ.get("JIG_USAGE_LOG"):
        return Path(env)
    return Path.home() / ".jigkit" / "skill-usage.jsonl"


def cmd_usage(rest: list[str]) -> None:
    """무엇이 실제로 불렸는지. 발견 단계를 끝내는 근거가 여기서 나온다.

    기록은 프로젝트를 가로질러 한 곳에 모인다 — "라이브러리를 프로필별로 어떻게
    나눌까" 는 한 프로젝트만 봐서는 답이 안 나오는 질문이기 때문이다.
    프로젝트별로 보려면 `--project <경로>`.

    **자동 정리는 하지 않는다.** 50세션에 한 번 불리는 스킬이 그 한 번에 결정적일 수
    있다. 숫자만 보여주고 자를지는 사람이 정한다.
    """
    only = _flag_value(rest, "--profile")
    only_project = _flag_value(rest, "--project")
    log = usage_log_path()

    events = []
    if log.is_file():
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # 훅이 쓰다 잘린 줄. 집계를 막지 않는다.

    projects = sorted({str(e.get("project")) for e in events if e.get("project")})
    if only_project:
        want = str(Path(only_project).resolve())
        events = [e for e in events if str(e.get("project")) == want]

    sessions = {e.get("session") for e in events if e.get("session")}
    print(f"스킬 호출 기록  {log}")
    print(f"  세션 {len(sessions)}회 · 호출 {len(events)}건"
          f" · 프로젝트 {len(projects)}곳" + (f" (필터: {only_project})" if only_project else ""))
    print()
    if not events:
        print("아직 기록이 없다. 프로필 세션에서 스킬이 한 번이라도 불리면 쌓인다.")
        return

    for n in ([only] if only else discover()):
        try:
            skills = sources.resolve(load_profile(n).get("skills"))
        except SourceError:
            skills = []
        dir_to_id = {sources.out_dir(s): s["id"] for s in skills}

        counts: dict[str, int] = {}
        last: dict[str, str] = {}
        for e in events:
            if e.get("plugin") != n:
                continue
            d = str(e.get("dir") or "")
            counts[d] = counts.get(d, 0) + 1
            last[d] = max(last.get(d, ""), str(e.get("ts") or ""))

        if not counts and not skills:
            continue

        # 이 프로필로 세션을 돈 적이 없으면 미사용 목록은 정보가 아니라 소음이다.
        if not counts:
            where = "이 프로젝트에" if only_project else "아직"
            print(f"{n}\n  {where} 호출 기록 없음 (선언 {len(skills)}개)\n")
            continue

        print(n)
        for d, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {dir_to_id.get(d, d):<34} {c:>4}회   최근 {last[d][:10]}")

        unused = [s["id"] for s in skills if sources.out_dir(s) not in counts]
        if unused:
            print(f"  선언했지만 한 번도 안 불림 — {len(unused)}개")
            for i in unused[:8]:
                print(f"      {i}")
            if len(unused) > 8:
                print(f"      … 외 {len(unused) - 8}개")
        print()

    # core 플러그인 등 프로필이 아닌 호출.
    other = sorted({str(e.get("plugin")) for e in events} - set(discover()))
    if other:
        print(f"(프로필 외 호출: {', '.join(other)})\n")

    if len(projects) > 1 and not only_project:
        print("기록에 들어온 프로젝트:")
        for p in projects:
            print(f"  {p}")
        print("  한 곳만 보려면: jig usage --project <경로>\n")

    print("정리는 사람이 한다 — 드물게 불리는 스킬이 그 한 번에 결정적일 수 있다.")
    print("좁히려면 profile.yaml 의 skills: 글롭을 실제로 쓰는 id 목록으로 바꾼다.")


def cmd_doctor(names: list[str], project: Path) -> None:
    failed = False
    for n in names or (discover() + discover_fixtures()):
        built = compile_profile(n, project)
        out, p = built["out"], built["profile"]
        settings = json.loads((out / "settings.json").read_text(encoding="utf-8"))
        deny = settings.get("permissions", {}).get("deny", [])
        skills = built["skills"]
        sk_tokens = sum(s["tokens"] for s in skills)
        approx = len((out / "system-prompt.md").read_text(encoding="utf-8")) // 4

        print(f"ok   {n:<12} 프롬프트 ~{approx}토큰 · 스킬 {len(skills)} (설명 ~{sk_tokens}t)"
              f" · deny {len(deny)}건")

        # 파일은 복사되지만 실행 환경은 따라오지 않는다. 조용히 실패하기 전에 알린다.
        if deps := [s["id"] for s in skills if "scripts" in s["extras"]]:
            shown = ", ".join(deps[:3]) + (f" 외 {len(deps) - 3}" if len(deps) > 3 else "")
            print(f"     note {n}: 런타임 의존성을 요구할 수 있는 스킬 {len(deps)}개 — {shown}")

        # [M] Write(...) 규칙은 차단되지 않는다. 조용히 틀리는 실패 모드라 여기서 잡는다.
        for rule in deny:
            if rule.startswith("Write("):
                print(f"     FAIL {n}: Write(...) 는 차단되지 않는다. Edit(...) 로 바꿔라 — {rule}")
                failed = True
        # 선언한 서버가 실제로 실렸는지 본다. 예전 검사는 `mcp.json` 파일 존재였는데
        # `compile_profile` 이 write_readback 으로 **항상** 쓰므로 발화할 수 없었다 —
        # 검사처럼 보이지만 아무것도 검사하지 않는 코드였다.
        if declared := set(p.get("mcp") or []):
            loaded = json.loads((out / "mcp.json").read_text(encoding="utf-8"))
            if missing := declared - set(loaded.get("mcpServers") or {}):
                print(f"     FAIL {n}: 선언한 MCP 서버가 mcp.json 에 없다 — {sorted(missing)}")
                failed = True

    # 픽스처는 단계가 아니므로 핸드오프 사슬에서 뺀다.
    failed |= _check_handoff_graph(names or discover())
    _check_source_drift()
    _note_pending()
    raise SystemExit(1 if failed else 0)


def _note_pending() -> None:
    """검증 대기 목록을 짚는다. 항목 셈법은 bin/jig-pending-note 의 것을 **불러 쓴다** —
    사본을 두면 갈라진다 (펜스 제외 수정을 두 곳에 따로 적용해야 했던 것이 그 증거)."""
    f = HARNESS / "probe" / "PENDING.md"
    if not f.is_file():
        return
    try:
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader(
            "_pending_note", str(HARNESS / "bin" / "jig-pending-note"))
        spec = importlib.util.spec_from_loader("_pending_note", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        n = mod.pending_entries(f.read_text(encoding="utf-8"))
    except Exception:
        return  # 알림 장치가 진단을 죽이면 안 된다 — 빌려 쓰는 훅과 같은 계약
    if n:
        print(f"     note pending 검증 {n}건 — probe/PENDING.md")


def _check_source_drift() -> None:
    """등록 SHA 와 캐시 HEAD 가 어긋났는지. 네트워크를 타지 않는다."""
    for ns, s in sorted(sources.load_sources().items()):
        cached, ref = sources.cached_sha(ns), str(s.get("ref") or "")
        if cached is None:
            print(f"     warn 소스 '{ns}' 캐시가 없다 — `jig sync {ns}`")
        elif cached != ref:
            print(f"     warn 소스 '{ns}' 캐시 {cached[:7]} ≠ 등록 {ref[:7]} — `jig sync {ns}`")


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

    스킬 실물(`skills/`)은 비교에서 뺀다. golden 의 일은 "컴파일러가 바뀌었나" 지
    "업스트림이 바뀌었나" 가 아니다. 넣으면 캐시를 gitignore 한 의미가 사라지고
    상류가 바뀔 때마다 깨진다. 대신 `manifest.json`(id + SHA + 내용 해시)이 비교된다.
    """
    import filecmp
    project = Path("/__golden__")
    ignore = filecmp.DEFAULT_IGNORES + ["skills"]
    golden = HARNESS / "tests" / "golden" / "claude"
    failed = False
    for n in names or (discover() + discover_fixtures()):
        out = compile_profile(n, project)["out"]
        exp = golden / n
        if update:
            import shutil
            if exp.exists():
                shutil.rmtree(exp)
            shutil.copytree(out, exp, ignore=shutil.ignore_patterns("skills"))
            print(f"updated golden/{n}")
            continue
        if not exp.is_dir():
            print(f"FAIL {n}: golden 이 없다. `jig golden --update {n}`")
            failed = True
            continue
        cmp = filecmp.dircmp(out, exp, ignore=ignore)
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
        die(commands.usage_line())
    cmd, rest = args[0], args[1:]
    project = Path(os.environ.get("HNS_PROJECT") or os.getcwd()).resolve()

    try:
        if cmd == "list":
            cmd_list()
        elif cmd == "source":
            cmd_source(rest)
        elif cmd == "sync":
            cmd_sync(rest)
        elif cmd == "skills":
            cmd_skills(rest)
        elif cmd == "usage":
            cmd_usage(rest)
        elif cmd == "touched":
            cmd_touched(rest)
        elif cmd == "docs":
            cmd_docs(rest)
        elif cmd == "selftest":
            cmd_selftest()
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
    except (BuildError, SourceError) as e:
        die(str(e))


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    main()
