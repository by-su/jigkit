#!/usr/bin/env python3
"""중립 profile.yaml + library/ -> Claude Code 플러그인 디렉터리.

Claude Code 문법을 아는 곳은 이 파일과 launch 인자 조립뿐이다.
스킬·에이전트는 library/ 에 한 벌만 살고, 여기서 프로필별로 복사된다.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path, PurePosixPath

import yaml

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

    role = HARNESS / "profiles" / profile["name"] / "ROLE.md"
    if not role.is_file():
        raise BuildError(f"{role} 이 없다.")
    parts.append(role.read_text(encoding="utf-8"))

    if done := profile.get("done_when") or []:
        lines = ["# 완료 정의", "", "아래를 전부 만족해야 이 단계가 끝난 것이다.", ""]
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


def copy_components(profile: dict, out: Path) -> None:
    """library/ 에서 이 프로필이 선언한 것만 복사한다."""
    for sid in profile.get("skills") or []:
        src = LIBRARY / "skills" / sid
        if not (src / "SKILL.md").is_file():
            raise BuildError(f"스킬 '{sid}' 이 없다: {src}/SKILL.md")
        shutil.copytree(src, out / "skills" / sid)

    for aid in profile.get("agents") or []:
        src = LIBRARY / "agents" / f"{aid}.md"
        if not src.is_file():
            raise BuildError(f"에이전트 '{aid}' 이 없다: {src}")
        (out / "agents").mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out / "agents" / f"{aid}.md")


def compile_profile(name: str, project: Path) -> dict:
    profile = load_profile(name)
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
            "description": f"jigkit 단계 프로필 — {profile.get('title', name)}",
            "author": {"name": "arto"},
        }, indent=2, ensure_ascii=False) + "\n",
    )
    copy_components(profile, out)
    write_readback(out / "settings.json",
                   json.dumps(build_settings(profile, project), indent=2, ensure_ascii=False) + "\n")
    write_readback(out / "mcp.json",
                   json.dumps(build_mcp(profile), indent=2, ensure_ascii=False) + "\n")
    write_readback(out / "system-prompt.md", build_system_prompt(profile))

    return {"profile": profile, "out": out}


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
