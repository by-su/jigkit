#!/usr/bin/env python3
"""중립 profile.yaml + library/ -> Claude Code 플러그인 디렉터리.

Claude Code 문법을 아는 곳은 이 파일과 launch 인자 조립뿐이다.
스킬은 등록된 오픈소스 캐시(`library/cache/`)나 로컬(`library/skills/`)에 한 벌만 살고,
에이전트·MCP 도 마찬가지다. 여기서 프로필이 선언한 것만 골라 복사한다.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path, PurePosixPath

import yaml

# sources 는 도구 중립이라 adapters/ 바로 아래 산다. 어떻게 실행되든 잡히게 한다.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sources  # noqa: E402

HARNESS = Path(__file__).resolve().parents[2]
LIBRARY = HARNESS / "library"
BUILD = HARNESS / "build" / "claude"

# 프로필이 선언할 수 있는 키. 오타를 조용히 넘기지 않는다.
KNOWN_KEYS = {
    "name", "title", "summary", "inputs", "inputs_optional", "outputs", "permissions",
    "skills", "agents", "mcp", "tools", "language", "bundled_skills",
    "budget_tokens", "done_when",
}


class BuildError(Exception):
    pass


def discover() -> list[str]:
    """profiles/ 를 글로빙해 발견한다. 레지스트리 파일을 두지 않는다 —
    프로필 추가가 코드 변경 0 이어야 하기 때문이다."""
    root = HARNESS / "profiles"
    if not root.is_dir():
        return []
    return sorted(
        d.name for d in root.iterdir()
        if not d.name.startswith("_") and (d / "profile.yaml").is_file()
    )


def discover_fixtures() -> list[str]:
    """`_` 로 시작하는 디렉터리 중 **컴파일 가능한** 것.

    `discover()` 는 `_` 접두사를 프로필이 아닌 것으로 거르지만, 그중 일부는 컴파일러
    분기 커버리지를 위해 golden 이 지나가야 한다. 목록을 코드에 박으면 `_fixture2` 를
    추가했을 때 조용히 빠지고 `ok` 만 찍힌다 — **커버리지가 있는 것처럼 보이는데 없는**
    상태이고, 픽스처가 애초에 없애려던 실패 모드가 한 층 위에서 재생산된다.
    그래서 여기도 글로빙한다.

    판별은 `name` 이 디렉터리명과 맞는지로 한다. `_template` 은 `name: CHANGEME` 라
    스스로 빠지므로 제외 목록이 필요 없다.
    """
    root = HARNESS / "profiles"
    if not root.is_dir():
        return []
    found = []
    for d in sorted(root.iterdir()):
        f = d / "profile.yaml"
        if not d.name.startswith("_") or not f.is_file():
            continue
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        if data.get("name") == d.name:
            found.append(d.name)
    return found


def load_profile(name: str) -> dict:
    f = HARNESS / "profiles" / name / "profile.yaml"
    if not f.is_file():
        raise BuildError(f"프로필 '{name}' 이 없다. `jig list` 로 확인.")
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    if data.get("name") != name:
        raise BuildError(f"{f}: name 이 '{data.get('name')}' 인데 디렉터리는 '{name}' 이다.")
    unknown = set(data) - KNOWN_KEYS
    if unknown:
        raise BuildError(f"{f}: 모르는 키 {sorted(unknown)}. 오타인가?")
    return data


def write_readback(path: Path, content: str) -> None:
    """P09 — 쓰기 경로마다 되읽기를 짝짓는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if path.read_text(encoding="utf-8") != content:
        raise BuildError(f"{path} 를 썼지만 되읽은 내용이 다르다.")


def abs_rule(project: Path, pattern: str) -> str:
    """프로젝트 상대 glob -> Claude 권한 규칙의 절대경로 형식(`//...`).
    probe #8 에서 이 형식이 실제로 차단하는 것을 확인했다 [M:CC-DENY-EDIT-BLOCKS]."""
    return "//" + str(project / pattern).lstrip("/")


def deny_glob(output: str) -> str:
    """산출물 경로 -> 차단 글롭.

    `docs/prd/{slug}.md` -> `docs/prd/**` · `src/**` 는 이미 글롭이라 그대로.
    """
    p = PurePosixPath(output)
    return output if "*" in p.name else f"{p.parent}/**"


def derived_deny_write(name: str) -> list[str]:
    """다른 단계의 산출물 전부를 차단 대상으로 유도한다.

    손으로 유지하면 프로필이 늘 때마다 기존 프로필들을 고쳐야 하고, 빠뜨리면
    조용히 구멍이 난다(실제로 세 군데 났었다). 규칙은 하나다 —
    **자기 outputs 외의 모든 단계 산출물은 못 쓴다.**

    아무 프로필도 소유하지 않는 경로(README.md 등)는 여기서 안 막힌다.
    그런 건 profile.yaml 의 permissions.deny_write 로 명시한다.
    """
    own = {deny_glob(o) for o in (load_profile(name).get("outputs") or [])}
    everything = {
        deny_glob(o)
        for n in discover()
        for o in (load_profile(n).get("outputs") or [])
    }
    return sorted(everything - own)


def build_settings(profile: dict, project: Path) -> dict:
    perms = profile.get("permissions") or {}
    deny: list[str] = []

    # [M:CC-DENY-NEEDS-EDIT-RULE] Write(path) 규칙은 파일 권한 검사에 걸리지 않는다.
    # CLI 가 직접 경고한다 — "Edit rules cover all file-editing tools".
    patterns = sorted(set(derived_deny_write(profile["name"])) | set(perms.get("deny_write") or []))
    for pat in patterns:
        deny.append(f"Edit({abs_rule(project, pat)})")
    for pat in perms.get("deny_read") or []:
        deny.append(f"Read({abs_rule(project, pat)})")

    settings: dict = {}
    if deny:
        settings["permissions"] = {"deny": deny}

    # [M:CC-BUNDLED-SKILLS-COST] 켜두면 번들 스킬 11개 = 약 1,776 토큰이 매 세션 올라간다.
    if not profile.get("bundled_skills", False):
        settings["disableBundledSkills"] = True

    if profile.get("language"):
        settings["language"] = profile["language"]
    return settings


def build_mcp(profile: dict) -> dict:
    """선언한 서버만 싣는다. 기본은 빈 집합.

    launch 는 이 파일을 --mcp-config 로 넘기고 --strict-mcp-config 를 붙인다
    → 다른 모든 MCP 설정이 무시된다 [D]."""
    servers = {}
    for sid in profile.get("mcp") or []:
        f = LIBRARY / "mcp" / f"{sid}.json"
        if not f.is_file():
            raise BuildError(f"MCP 서버 '{sid}' 정의가 없다: {f}")
        servers[sid] = json.loads(f.read_text(encoding="utf-8"))
    return {"mcpServers": servers}


def build_system_prompt(profile: dict) -> str:
    parts = [(HARNESS / "core" / "PREAMBLE.md").read_text(encoding="utf-8")]

    brief = HARNESS / "profiles" / profile["name"] / "BRIEF.md"
    if not brief.is_file():
        raise BuildError(f"{brief} 이 없다.")
    parts.append(brief.read_text(encoding="utf-8"))

    if done := profile.get("done_when") or []:
        lines = ["# 완료 정의", "", "아래를 전부 만족해야 이 프로필의 작업이 끝난 것이다.", ""]
        for item in done:
            if isinstance(item, dict) and "cmd" in item:
                lines.append(f"- [실행] {item['cmd']}")
            else:
                lines.append(f"- {item}")
        parts.append("\n".join(lines))

    ins = profile.get("inputs") or []
    opt = profile.get("inputs_optional") or []
    outs = profile.get("outputs") or []
    if ins or opt or outs:
        lines = ["# 이 단계의 입출력", ""]
        if ins:
            lines += ["읽는다 (입력이지 작업 대상이 아니다):"] + [f"- `{p}`" for p in ins] + [""]
        if opt:
            lines += ["있으면 읽는다:"] + [f"- `{p}`" for p in opt] + [""]
        if outs:
            lines += ["쓴다 (그 밖의 경로는 권한으로 막혀 있다):"] + [f"- `{p}`" for p in outs]
        parts.append("\n".join(lines))

    return "\n\n---\n\n".join(p.strip() for p in parts) + "\n"


def copy_components(profile: dict, out: Path, skills: list[dict]) -> None:
    """이 프로필이 선언한 것만 복사한다.

    스킬은 `library/cache/<ns>/` (등록된 오픈소스) 또는 `library/skills/` (로컬)에서 온다.
    `copytree` 라서 `SKILL.md` 뿐 아니라 `scripts/` · `references/` · `templates/` 가
    통째로 따라온다. 부속 파일은 스킬이 호출될 때만 읽히므로 기동 비용이 0 이다 (P03).
    """
    for s in skills:
        shutil.copytree(s["path"], out / "skills" / sources.out_dir(s))

    for aid in profile.get("agents") or []:
        src = LIBRARY / "agents" / f"{aid}.md"
        if not src.is_file():
            raise BuildError(f"에이전트 '{aid}' 이 없다: {src}")
        (out / "agents").mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out / "agents" / f"{aid}.md")


def _skill_hash(d: Path) -> str:
    """스킬 디렉터리 내용 해시. 상류 사본을 커밋하지 않고도 무엇을 실었는지 고정된다."""
    h = hashlib.sha256()
    for f in sorted(p for p in d.rglob("*") if p.is_file()):
        h.update(str(f.relative_to(d)).encode("utf-8"))
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def build_manifest(profile: dict, skills: list[dict]) -> dict:
    """무엇을 어느 커밋에서 실었는지. golden 은 스킬 실물 대신 이걸 비교한다.

    golden 의 일은 "컴파일러가 바뀌었나" 지 "업스트림이 바뀌었나" 가 아니다.
    훅이 보고하는 `<프로필>:<디렉터리>` 를 원래 id 로 되돌리는 것도 이 표가 맡는다 [M].
    """
    registered = sources.load_sources()
    return {
        "profile": profile["name"],
        "skills": [
            {
                "id": s["id"],
                "dir": sources.out_dir(s),
                "source": s.get("ns"),
                "ref": (registered.get(s["ns"]) or {}).get("ref") if s.get("ns") else None,
                "sha256": _skill_hash(s["path"]),
                "description_tokens": s["tokens"],
            }
            for s in skills
        ],
    }


def install_hooks(out: Path) -> None:
    """훅을 **플러그인 안에** 심는다.

    [M] 플러그인이 소유한 `hooks/hooks.json` 은 `--plugin-dir` 로 붙여도 발화하고
    `${CLAUDE_PLUGIN_ROOT}` 가 확장된다 (probe/results/skill-usage.md).
    그래서 `settings.json` 에 이 머신의 절대경로를 박지 않아도 되고,
    golden 출력이 머신 독립을 유지한다.

    셋을 심는다.
    - `log-skill`  스킬 호출 기록 (관찰 — 절대 막지 않는다)
    - `commit-gate` 커밋 직전 문서 영향 주입 (jigkit 저장소 안에서만 동작)
    - `pending-note` 세션 시작 때 검증 대기 목록 주입 (jigkit 저장소 안에서만 동작)
    """
    for name in ("jig-log-skill", "jig-commit-gate", "jig-pending-note"):
        src = HARNESS / "bin" / name
        if not src.is_file():
            raise BuildError(f"훅 스크립트가 없다: {src}")
        dst = out / "hooks" / name.removeprefix("jig-")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    # [M] 훅은 **동기적으로** 막는다 — sleep 8 을 걸면 호출마다 8초가 그대로 더해진다.
    # 한 줄 append 는 밀리초지만, 디스크가 차거나 NFS 가 멎으면 함께 멎는다.
    # timeout 이 그 상한을 실제로 거는 것도 쟀다 (probe/results/skill-usage.md).
    # 타임아웃된 훅은 동작을 막지 않는다 — 둘 다 알림 장치라 fail open 이 맞는 방향이다.
    write_readback(out / "hooks" / "hooks.json", json.dumps({
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Skill",
                    "hooks": [{"type": "command",
                               "command": "${CLAUDE_PLUGIN_ROOT}/hooks/log-skill",
                               "timeout": 5}],
                },
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command",
                               "command": "${CLAUDE_PLUGIN_ROOT}/hooks/commit-gate",
                               "timeout": 10}],
                },
            ],
            # stdout 주입 실측(probe/results/session-start.md)은 **settings 경로**를
            # 잰 것이다. 플러그인 경로의 SessionStart 발화는 아직 미실측 — 확인
            # 방법과 함께 probe/PENDING.md 에 등록돼 있다. 안 발화하면 jig 세션의
            # 검증 대기 주입이 조용히 빠진다 (fail-silent).
            "SessionStart": [
                {
                    "matcher": "startup",
                    "hooks": [{"type": "command",
                               "command": "${CLAUDE_PLUGIN_ROOT}/hooks/pending-note",
                               "timeout": 5}],
                },
            ],
        },
    }, indent=2, ensure_ascii=False) + "\n")


def compile_profile(name: str, project: Path) -> dict:
    profile = load_profile(name)
    skills = sources.resolve(profile.get("skills"))
    out = BUILD / name

    # 결정적 출력을 위해 매번 지우고 다시 만든다. golden 비교가 성립하려면 필수다.
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    write_readback(
        out / ".claude-plugin" / "plugin.json",
        json.dumps({
            "name": name,
            "version": "0.1.0",
            "description": f"jigkit 프로필 — {profile.get('title', name)}",
            "author": {"name": "arto"},
        }, indent=2, ensure_ascii=False) + "\n",
    )
    copy_components(profile, out, skills)
    install_hooks(out)
    write_readback(out / "manifest.json",
                   json.dumps(build_manifest(profile, skills), indent=2, ensure_ascii=False) + "\n")
    write_readback(out / "settings.json",
                   json.dumps(build_settings(profile, project), indent=2, ensure_ascii=False) + "\n")
    write_readback(out / "mcp.json",
                   json.dumps(build_mcp(profile), indent=2, ensure_ascii=False) + "\n")
    write_readback(out / "system-prompt.md", build_system_prompt(profile))

    return {"profile": profile, "out": out, "skills": skills}


def launch_argv(name: str, project: Path) -> list[str]:
    built = compile_profile(name, project)
    out, profile = built["out"], built["profile"]

    argv = [
        "claude",
        "--plugin-dir", str(HARNESS / "core"),
        "--plugin-dir", str(out),
        "--settings", str(out / "settings.json"),
        "--append-system-prompt-file", str(out / "system-prompt.md"),
        # 프로젝트/로컬 설정이 프로필 권한을 덮지 못하게 한다.
        "--setting-sources", "user",
        # 선언한 서버만. 다른 모든 MCP 설정을 무시한다.
        "--mcp-config", str(out / "mcp.json"),
        "--strict-mcp-config",
    ]
    if tools := profile.get("tools") or []:
        argv += ["--tools", ",".join(tools)]
    return argv
