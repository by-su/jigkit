#!/usr/bin/env python3
"""스택 배치 — Claude Code 문법을 아는 쪽. **파일을 쓰는 유일한 스택 경로다.**

여기 있는 것은 흔들리면 안 되는 것들이다: 훅 JSON · 디스패처 스크립트 · 설정 파일.
MCP 정의는 **여기서 쓰지 않는다** — 카탈로그에 한 벌만 살고 프로필이 id 로 켠다.
프로젝트 생성과 의존성 설치는 스킬이 셸에서 한다 — 대화형 프롬프트와 버전마다
바뀌는 인자를 파이썬으로 감싸면 실패 처리를 전부 다시 써야 하고, 그때부터 에이전트가
실행기를 우회한다.

**이벤트당 훅 항목은 하나다.** matcher 는 도구 이름만 거르고 경로는 모르며, 매칭되는 훅은
전부 병렬로 돈다 [D]. 도구마다 항목을 등록하면 `.py` 하나 고칠 때 Biome·Prisma 훅까지 뜬다.
그래서 확장자 분기는 디스패처 **안**으로 들어간다 — 스택 둘을 겹쳐도 `.py` 편집에 py 분기만
1회 돈다 [M] (probe/results/stack-hooks.md).

항목을 배열에 덧붙이지 않고 command 문자열로 찾아 교체하는 이유는 중복 발화가 아니다 —
같은 파일 안의 동일 command 는 어차피 한 번만 돈다 [M]. 재적용마다 항목이 늘어 파일이
읽을 수 없게 되고, 사람이 손으로 넣은 훅과 우리 항목을 구별할 수 없기 때문이다.

훅은 대상 프로젝트 `.claude/settings.json` 에만 쓴다. 같은 handler 는 settings 파일 간에는
dedupe 되지만 **플러그인 사본은 별도로 남아서** [D] 프로필 빌드에 실으면 두 번 돈다.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import mdblock
import stacks
from build import write_readback

FORMAT_HOOK = ".claude/hooks/jig-format"
GATE_HOOK = ".claude/hooks/jig-gate"
# 배치와 대조가 같은 구간을 봐야 하므로 마커는 stacks.py 에 한 벌만 산다.
MARKERS = stacks.HOOK_MARKERS

_FORMAT_SHELL = '''#!/usr/bin/env python3
"""PostToolUse 훅 — 고친 파일에 그 확장자의 도구를 돌린다. `jig stack apply` 가 생성한다.

마커 사이만 생성물이다. 밖에 쓴 것은 재적용에도 살아남는다.
항상 exit 0 — 포매터가 세션을 막으면 안 된다. 실패는 stderr 로 보인다.
"""
import json, shlex, subprocess, sys

BRANCHES = [
{branches}]

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)
path = (payload.get("tool_input") or {{}}).get("file_path") or ""
if not path:
    sys.exit(0)

for exts, cmd in BRANCHES:
    if any(path.endswith(e) for e in exts):
        done = subprocess.run(cmd.replace("{{file}}", shlex.quote(path)), shell=True,
                              capture_output=True, text=True)
        if done.returncode != 0:
            sys.stderr.write((done.stderr or done.stdout or "").strip()[:2000] + "\\n")
sys.exit(0)
'''

_GATE_SHELL = '''#!/usr/bin/env python3
"""PreToolUse 훅 — 커밋 직전 게이트. `jig stack apply` 가 생성한다.

막을 때만 exit 2 로 나가고 이유를 stderr 에 쓴다 — 그 stderr 가 모델에게 그대로 간다.
git commit 이 아닌 Bash 는 그냥 통과시킨다. 오류가 나도 통과시킨다(알림 장치다).
"""
import json, re, subprocess, sys

CHECKS = [
{checks}]

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)
command = (payload.get("tool_input") or {{}}).get("command") or ""
if not re.search(r"\\bgit\\b.*\\bcommit\\b", command):
    sys.exit(0)

failed = []
for name, cmd in CHECKS:
    done = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if done.returncode != 0:
        failed.append((name, cmd, (done.stdout or done.stderr or "").strip()[:1500]))

if failed:
    lines = ["커밋 전 게이트가 막았다 — 통과시킬 것은 통과시키고 나머지는 고친다.", ""]
    for name, cmd, out in failed:
        lines += [f"  {{name}}: {{cmd}}", *(f"    {{l}}" for l in out.splitlines()[:20]), ""]
    sys.stderr.write("\\n".join(lines))
    sys.exit(2)
sys.exit(0)
'''


_ID_COMMENT = stacks.ID_COMMENT


def _merge(path: Path, new_lines: list[str], known: dict[str, str]) -> tuple[str, list[str]]:
    """블록을 **id 로 병합**하고 (본문, 은퇴한 id 목록) 을 돌려준다.

    통째로 갈아 끼우면 `jig stack apply typescript` 가 앞서 넣은 python 분기를 지운다 —
    실측했다: 훅이 조용히 사라지고 배치 모양(항목 1개)은 그대로여서 아무도 눈치채지 못한다
    (probe/results/stack-hooks.md).

    그래서 기존 분기를 **세 갈래로** 가른다. 판정 근거는 카탈로그이고, 프로젝트별 적용 기록은
    필요하지 않다:

    - 이번 조합에 있다 → 이번 정의로 갱신
    - 이번 조합엔 없지만 **카탈로그에 있다**(`known`) → 다른 스택이 쓰는 것이므로 유지.
      단 그 줄을 그대로 두지 않고 **카탈로그 정의로 다시 렌더**한다 — 그래야 디스패처가
      `(카탈로그, 살아 있는 id 집합)` 의 함수가 되고, 옛 명령이 남는 표류가 없다.
    - 카탈로그에 없다 → **은퇴**. 지우고 호출자가 출력한다.

    마커 **안**은 생성물 영역이므로 손으로 넣은 줄도 은퇴 대상이다. 조용히 지우지 않고
    목록으로 돌려주는 것이 그에 대한 대가다.
    """
    kept: dict[str, str] = {}
    retired: list[str] = []
    if path.is_file():
        old = path.read_text(encoding="utf-8")
        if MARKERS[0] not in old:
            # 우리가 만든 파일이 아니다. 통째로 덮으면 사람이 쓴 훅이 사라진다.
            raise stacks.StackError(
                f"{path} 가 이미 있는데 생성 마커가 없다. 우리 것이 아니므로 덮지 않는다 — "
                f"내용을 확인하고 마커를 넣거나 파일을 옮긴다"
            )
        inside = old.split(MARKERS[0], 1)[1].split(MARKERS[1], 1)[0]
        for line in inside.strip("\n").splitlines():
            if not line.strip():
                continue
            m = _ID_COMMENT.search(line)
            if not m:
                retired.append("(id 주석이 없는 줄)")
            elif m.group(1) in known:
                kept[m.group(1)] = known[m.group(1)]
            else:
                retired.append(m.group(1))
    for line in new_lines:
        if m := _ID_COMMENT.search(line):
            kept[m.group(1)] = line  # 같은 id 는 이번 정의로 갱신한다
    return "\n".join(kept.values()), retired


def _write_block(path: Path, template: str, body: str) -> str:
    if path.is_file():
        return mdblock.splice(path.read_text(encoding="utf-8"), *MARKERS, body)
    wrapped = "\n".join([MARKERS[0], body, MARKERS[1]]) + "\n"
    return template.format(branches=wrapped, checks=wrapped)


def _format_lines(items: list[dict]) -> list[str]:
    out = []
    for item in items:
        hook = item["hook"]
        exts = ", ".join(repr(e) for e in hook["ext"])
        out.append(f"    ([{exts}], {hook['run']!r}),  # {item['id']}")
    return out


def _gate_lines(items: list[dict]) -> list[str]:
    return [f"    ({item['id']!r}, {item['gate']['run']!r}),  # {item['id']}"
            for item in items]


def _settings_with(settings: dict, event: str, matcher: str, command: str) -> bool:
    """이벤트에 우리 디스패처 핸들러가 하나 있게 만든다. 바뀌었으면 True.

    배열에 덧붙이지 않고 **command 문자열로 핸들러를 찾아** 그 자리만 손본다.
    항목(entry) 통째로 갈아 끼우면 사람이 같은 항목에 넣어 둔 다른 훅이 사라진다 —
    그리고 matcher 도 건드리지 않는다. 우리 핸들러가 남의 항목 안에 있다면 그건 사람이
    그렇게 둔 것이므로 그 항목의 조건은 그 사람 것이다.
    """
    # 남의 파일이므로 형태를 가정하지 않는다 — `{"hooks": null}` 이나 배열이 들어와도
    # 트레이스백이 아니라 진단으로 나가야 한다.
    if settings.get("hooks") is None:
        settings["hooks"] = {}
    hooks = settings["hooks"]
    if not isinstance(hooks, dict):
        raise stacks.StackError("settings.json 의 hooks 가 객체가 아니다 — 손대지 않는다")
    if hooks.get(event) is None:
        hooks[event] = []
    entries = hooks[event]
    if not isinstance(entries, list):
        raise stacks.StackError(f"settings.json 의 hooks.{event} 가 배열이 아니다 — 손대지 않는다")

    want = {"type": "command", "command": f'"$CLAUDE_PROJECT_DIR"/{command}'}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        handlers = entry.get("hooks") or []
        if not isinstance(handlers, list):
            continue
        for i, handler in enumerate(handlers):
            if not isinstance(handler, dict):
                continue
            if command in (handler.get("command") or ""):
                if handler == want:
                    return False
                handlers[i] = want
                return True
    entries.append({"matcher": matcher, "hooks": [want]})
    return True


def apply(combo: dict, project: Path, write: bool) -> list[str]:
    """배치한다(또는 무엇을 배치할지 돌려준다). 반환은 사람이 읽을 줄 목록."""
    out: list[str] = []
    hook_items = [i for i in combo["items"] if i["surface"] == "hook"]
    gate_items = [i for i in combo["items"] if i["surface"] == "gate"]

    if not project.is_dir():
        raise stacks.StackError(
            f"{project} 가 없다. 새 프로젝트라면 먼저 "
            f"`jig stack show {combo['spec']} --plan {project}` 의 create 단계를 돌린다"
        )

    # 1) 디스패처 — 이벤트당 하나. 스택이 몇 개든 항목은 늘지 않는다.
    #
    # 카탈로그 전체를 표면별로 미리 렌더해 둔다. 이번 조합에 없는 분기를 "다른 스택이
    # 쓰는 것"(유지)과 "은퇴한 항목"(제거)으로 가르는 근거가 이것이다 — id 가 카탈로그에
    # 있고 **그 디스패처에 맞는 표면**일 때만 살린다. hook 이었던 항목이 library 로 바뀌면
    # 그것도 은퇴다.
    catalog = stacks.catalog_items()
    for items, rel, template, lines_of, surface, label in (
        (hook_items, FORMAT_HOOK, _FORMAT_SHELL, _format_lines, "hook", "포맷 훅"),
        (gate_items, GATE_HOOK, _GATE_SHELL, _gate_lines, "gate", "커밋 게이트"),
    ):
        if not items:
            continue
        known = {i["id"]: lines_of([i])[0]
                 for i in catalog.values() if i["surface"] == surface}
        path = project / rel
        body, retired = _merge(path, lines_of(items), known)
        content = _write_block(path, template, body)
        changed = not path.is_file() or path.read_text(encoding="utf-8") != content
        ids = ", ".join(i["id"] for i in items)
        out.append(f"{'쓴다' if changed else '이미 최신'}  {rel}  ({label}: {ids})")
        for gone in retired:
            out.append(f"  은퇴  {gone}  (카탈로그에 없다 — 분기를 지운다)")
        if write and changed:
            write_readback(path, content)
            path.chmod(0o755)

    # 2) settings.json — command 문자열로 식별해 교체한다
    spath = project / ".claude" / "settings.json"
    settings = {}
    if spath.is_file():
        try:
            settings = json.loads(spath.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise stacks.StackError(f"{spath} 를 파싱할 수 없다: {e}") from e
        if not isinstance(settings, dict):
            raise stacks.StackError(f"{spath} 의 최상위가 객체가 아니다 — 손대지 않는다")
    touched = False
    if hook_items:
        touched |= _settings_with(settings, "PostToolUse", "Edit|Write", FORMAT_HOOK)
    if gate_items:
        touched |= _settings_with(settings, "PreToolUse", "Bash", GATE_HOOK)
    if hook_items or gate_items:
        out.append(f"{'쓴다' if touched else '이미 최신'}  .claude/settings.json  "
                   f"(이벤트당 항목 1개)")
        if write and touched:
            write_readback(spath, json.dumps(settings, indent=2, ensure_ascii=False) + "\n")

    # 3) 설정 파일 템플릿 — 없을 때만. 있으면 건드리지 않고 알린다.
    for item in combo["items"]:
        tname = item.get("template")
        if not tname:
            continue
        src = stacks.STACKS / "templates" / tname
        if not src.is_dir():
            raise stacks.StackError(f"템플릿이 없다: library/stacks/templates/{tname}")
        for f in sorted(p for p in src.rglob("*") if p.is_file()):
            rel = f.relative_to(src)
            dst = project / rel
            if dst.exists():
                out.append(f"건너뜀  {rel}  (이미 있다 — 덮지 않는다)")
                continue
            out.append(f"쓴다  {rel}  ({item['id']} 템플릿)")
            if write:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)

    # 4) MCP — **여기서 파일을 만들지 않는다.**
    #
    #    예전에는 조합의 mcp 항목마다 `library/mcp/<id>.json` 을 미리 깔았다. 지금은
    #    프로필이 카탈로그 id 를 바로 켜므로 그 파일이 필요 없고, 만들면 해롭다:
    #    빌드는 파일을 카탈로그보다 우선하므로 **한 번 깔린 사본이 이후의 카탈로그
    #    수정을 영구히 가린다.** 옛 정의(`@posthog/mcp-server`)가 깔린 기계에서는
    #    카탈로그를 고쳐도 세션에 옛 정의가 실리고, apply 는 "이미 있음" 이라고만 한다.
    #    정의는 카탈로그 한 곳에만 산다 — 파일은 사람이 override 하려 할 때만 만든다.
    #
    #    켜는 것은 사람이 한다: 프로필은 --strict-mcp-config 라 대상 프로젝트의
    #    .mcp.json 을 무시하고, 도구 하나당 ~15토큰이 붙는다 [M]
    #    (probe/results/mcp-env.md).
    pending_mcp = [i["id"] for i in combo["items"] if i["surface"] == "mcp"]
    for item in (i for i in combo["items"] if i["surface"] == "mcp"):
        if stacks.mcp_override_differs(item["id"], item["mcp"]):
            out.append(f"주의  library/mcp/{item['id']}.json 이 카탈로그와 다르다 "
                       f"— 이 파일이 이깁니다. 의도한 override 가 아니면 지운다")
    if pending_mcp:
        out += ["", "MCP 는 자동으로 켜지 않는다. 쓰려면 프로필에 직접 적는다:",
                f"    mcp: [{', '.join(pending_mcp)}]",
                "    그다음 `jig budget <프로필>` 로 기동 비용을 다시 잰다."]

    agents = [i for i in combo["items"] if i["surface"] == "agents"]
    if agents:
        out += ["", "agents 표면은 업스트림 init 이 만든다 — apply 가 아니라 plan 의 init 단계다:"]
        out += [f"    {i['init']}" for i in agents if i.get("init")]
    return out
