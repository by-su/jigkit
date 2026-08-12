#!/usr/bin/env python3
"""오픈소스 스킬 저장소 등록 · 캐시 · 탐색.

도구 중립이다. Claude Code 문법을 모른다 — 어댑터가 이 모듈을 쓴다.

**저장소 내용은 jigkit 이 소유하지 않는다.** `library/cache/` 는 언제든 지워도 되는
파생물이고, 커밋되는 진실은 `library/sources.yaml` 의 링크 + SHA 뿐이다.
그래서 업스트림 변경은 사본 diff 가 아니라 **SHA 한 줄 diff** 로 리뷰를 통과한다.
"""
from __future__ import annotations

import fnmatch
import re
import shutil
import subprocess
from pathlib import Path

import yaml

HARNESS = Path(__file__).resolve().parents[1]
SOURCES = HARNESS / "library" / "sources.yaml"
CACHE = HARNESS / "library" / "cache"
LOCAL_SKILLS = HARNESS / "library" / "skills"

# 스킬 탐색에서 건너뛸 디렉터리. 상류가 예제·테스트에 SKILL.md 를 두는 경우가 있다.
SKIP_PARTS = {".git", "node_modules", "__pycache__", ".venv"}

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---", re.DOTALL)

_HEADER = """\
# 오픈소스 스킬 저장소 등록부.
#
# 여기에는 **링크와 SHA 만** 산다. 저장소 내용은 library/cache/ 로 받아두고
# 커밋하지 않는다 (.gitignore). 캐시는 지워도 되며 `jig sync` 로 복원된다.
#
#   jig source add https://github.com/anthropics/skills
#   jig sync                  등록된 ref 대로 캐시를 맞춘다
#   jig sync --check          최신 SHA 만 확인 (캐시·이 파일 불변)
#   jig sync --update <ns>    최신으로 올리고 무엇이 바뀌었는지 보여준다
#
# ref 는 손으로 적지 않는다 — jig sync 가 받은 커밋을 되써넣는다.
"""


class SourceError(Exception):
    pass


# ---------------------------------------------------------------- git

def _git(*args: str, cwd: Path | None = None) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd) if cwd else None,
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise SourceError(f"git {' '.join(args)} 실패: {proc.stderr.strip()[:300]}")
    return proc.stdout.strip()


def ls_remote(url: str) -> str:
    """원격 기본 브랜치의 SHA. 데이터 전송이 없어 --check 가 싸다."""
    out = _git("ls-remote", url, "HEAD")
    if not out:
        raise SourceError(f"{url} 의 HEAD 를 읽지 못했다. URL 을 확인한다.")
    return out.split()[0]


# ---------------------------------------------------------------- 등록부

def load_sources() -> dict:
    if not SOURCES.is_file():
        return {}
    data = yaml.safe_load(SOURCES.read_text(encoding="utf-8")) or {}
    return data.get("sources") or {}


def save_sources(sources: dict) -> None:
    """P09 — 쓰고 되읽는다. 주석 머리말은 코드가 소유하므로 왕복해도 살아남는다."""
    body = yaml.safe_dump({"sources": sources}, allow_unicode=True, sort_keys=True)
    content = _HEADER + "\n" + body
    SOURCES.parent.mkdir(parents=True, exist_ok=True)
    SOURCES.write_text(content, encoding="utf-8")
    if SOURCES.read_text(encoding="utf-8") != content:
        raise SourceError(f"{SOURCES} 를 썼지만 되읽은 내용이 다르다.")


def require(ns: str) -> dict:
    sources = load_sources()
    if ns not in sources:
        known = ", ".join(sorted(sources)) or "(없음)"
        raise SourceError(f"소스 '{ns}' 가 등록돼 있지 않다. 등록된 것: {known}")
    return sources[ns]


def ns_from_url(url: str) -> str:
    """https://github.com/anthropics/skills -> anthropics

    저장소 이름(`skills`)이 아니라 **소유자**를 쓴다. 저장소 이름은 `skills`,
    `agent-skills` 처럼 겹치기 쉬워 네임스페이스로 못 쓴다.
    """
    s = url.rstrip("/")
    if s.endswith(".git"):
        s = s[: -len(".git")]
    parts = [p for p in re.split(r"[:/]", s) if p]
    raw = parts[-2] if len(parts) >= 2 else parts[-1]
    ns = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    if not ns:
        raise SourceError(f"{url} 에서 네임스페이스를 뽑지 못했다. --as 로 지정한다.")
    return ns


def add_source(url: str, ns: str | None = None) -> tuple[str, str]:
    ns = ns or ns_from_url(url)
    sources = load_sources()
    if ns in sources:
        raise SourceError(
            f"소스 '{ns}' 는 이미 등록돼 있다 ({sources[ns].get('repo')}). "
            f"다른 이름을 쓰려면 --as <이름>."
        )
    sha = ls_remote(url)
    sources[ns] = {"repo": url, "ref": sha}
    save_sources(sources)
    return ns, sha


# ---------------------------------------------------------------- 캐시

def cached_sha(ns: str) -> str | None:
    d = CACHE / ns
    if not (d / ".git").is_dir():
        return None
    try:
        return _git("rev-parse", "HEAD", cwd=d)
    except SourceError:
        return None


def fetch(ns: str, ref: str | None = None) -> str:
    """`library/cache/<ns>/` 를 지정 SHA 로 맞춘다.

    `clone --depth 1` 은 임의 SHA 를 체크아웃하지 못하므로 init + fetch <sha> 를 쓴다.
    shallow 여도 해당 커밋의 트리는 전부 오므로 diff 와 ls-tree 가 성립한다.
    """
    src = require(ns)
    ref = ref or src.get("ref") or ls_remote(src["repo"])
    d = CACHE / ns

    if not (d / ".git").is_dir():
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
        _git("init", "-q", cwd=d)
        _git("remote", "add", "origin", src["repo"], cwd=d)
    else:
        # 등록부의 URL 이 바뀌었을 수 있다.
        _git("remote", "set-url", "origin", src["repo"], cwd=d)

    _git("fetch", "-q", "--depth", "1", "origin", ref, cwd=d)
    _git("checkout", "-q", "--force", "--detach", "FETCH_HEAD", cwd=d)
    return ref


# ---------------------------------------------------------------- 스킬 탐색

def _is_skipped(path: Path, root: Path) -> bool:
    return any(part in SKIP_PARTS for part in path.relative_to(root).parts)


def discover_skills(ns: str) -> dict[str, Path]:
    """캐시를 재귀 탐색해 `SKILL.md` 를 찾는다. 스킬 id 는 부모 디렉터리 이름.

    저장소마다 레이아웃이 다르다 — 루트 직하, `skills/`, `document-skills/`,
    `.claude-plugin/` 을 가진 플러그인 통째. 소스마다 경로를 적게 하는 대신
    탐색으로 흡수한다.
    """
    d = CACHE / ns
    if not d.is_dir():
        raise SourceError(f"소스 '{ns}' 캐시가 없다. `jig sync {ns}` 를 먼저 실행한다.")

    found: dict[str, list[Path]] = {}
    for skill_md in sorted(d.rglob("SKILL.md")):
        if _is_skipped(skill_md, d) or skill_md.parent == d:
            continue
        found.setdefault(skill_md.parent.name, []).append(skill_md.parent)

    dupes = {k: v for k, v in found.items() if len(v) > 1}
    if dupes:
        lines = [
            f"  {k}: " + ", ".join(str(p.relative_to(d)) for p in v)
            for k, v in sorted(dupes.items())
        ]
        raise SourceError(
            f"소스 '{ns}' 안에 같은 이름의 스킬이 여러 개다:\n" + "\n".join(lines)
        )
    return {k: v[0] for k, v in found.items()}


def parse_skill(d: Path) -> dict:
    """SKILL.md frontmatter 에서 설명을 뽑고 부속 디렉터리 유무를 본다.

    [M] 스킬의 **정체성은 디렉터리 이름**이다 — frontmatter 의 `name` 은 무시된다
    (probe/results/skill-usage.md #4). 그래서 여기서 `name` 을 읽지 않는다.
    """
    text = (d / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    meta: dict = {}
    if m := _FRONTMATTER.match(text):
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            meta = {}
    desc = " ".join(str(meta.get("description") or "").split())
    extras = sorted(
        p.name for p in d.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )
    return {"path": d, "description": desc, "tokens": len(desc) // 4, "extras": extras}


def catalog() -> tuple[dict[str, dict], list[str]]:
    """`<ns>/<스킬>` -> 정보. 캐시가 없는 소스는 두 번째 반환값에 모은다."""
    out: dict[str, dict] = {}
    missing: list[str] = []
    for ns in sorted(load_sources()):
        if not (CACHE / ns).is_dir():
            missing.append(ns)
            continue
        for name, path in discover_skills(ns).items():
            out[f"{ns}/{name}"] = {"ns": ns, "name": name, **parse_skill(path)}
    return out, missing


def out_dir(skill: dict) -> str:
    """빌드 출력에서 쓸 디렉터리 이름. `anthropics/pdf` -> `anthropics-pdf`.

    [M] `--plugin-dir` 는 플래그당 플러그인 루트 하나이고 부모를 스캔하지 않으며
    (probe/results/phase0.md #5), 스킬 정체성은 디렉터리 이름이다 (skill-usage.md #4).
    따라서 중첩을 만들지 않고 평탄화해야 하고, 평탄화하면 소스 간 이름 충돌도 사라진다.
    """
    return f"{skill['ns']}-{skill['name']}" if skill.get("ns") else skill["name"]


def resolve(entries: list[str] | None) -> list[dict]:
    """profile.yaml 의 `skills:` 항목을 실제 스킬 목록으로 편다.

    - `/` 가 없으면 `library/skills/<id>/` 의 로컬 스킬
    - `*` 나 `?` 가 있으면 글롭 — 발견 단계에 `anthropics/*` 로 통째 켠다
    - 그 밖에는 정확 일치

    결정적 출력을 위해 정렬 + 중복 제거한다.
    """
    cat, missing = catalog()
    picked: dict[str, dict] = {}

    for entry in entries or []:
        if "/" not in entry:
            d = LOCAL_SKILLS / entry
            if not (d / "SKILL.md").is_file():
                raise SourceError(f"스킬 '{entry}' 이 없다: {d / 'SKILL.md'}")
            picked[entry] = {"id": entry, "ns": None, "name": entry, **parse_skill(d)}
            continue

        if "*" in entry or "?" in entry:
            hits = fnmatch.filter(cat, entry)
            if not hits:
                hint = f" 캐시 없는 소스: {', '.join(missing)} — `jig sync` 실행." if missing else ""
                raise SourceError(f"'{entry}' 에 맞는 스킬이 없다.{hint}")
            for h in hits:
                picked[h] = {"id": h, **cat[h]}
            continue

        if entry not in cat:
            ns = entry.split("/", 1)[0]
            if ns in missing:
                raise SourceError(f"스킬 '{entry}': 소스 '{ns}' 캐시가 없다. `jig sync {ns}` 실행.")
            raise SourceError(f"스킬 '{entry}' 을 찾지 못했다. `jig skills` 로 확인.")
        picked[entry] = {"id": entry, **cat[entry]}

    skills = [picked[k] for k in sorted(picked)]

    # 평탄화가 두 스킬을 같은 디렉터리로 보내면 조용히 덮어쓰게 된다. 크게 잡는다.
    seen: dict[str, str] = {}
    for s in skills:
        d = out_dir(s)
        if d in seen:
            raise SourceError(
                f"스킬 '{seen[d]}' 과 '{s['id']}' 이 같은 출력 디렉터리 '{d}' 로 평탄화된다. "
                f"둘 중 하나를 빼야 한다."
            )
        seen[d] = s["id"]
    return skills


# ---------------------------------------------------------------- 업데이트 비교

def _skill_dirs_at(ns: str, sha: str) -> dict[str, str]:
    """특정 커밋에서의 `스킬이름 -> 저장소내 경로`. 작업 트리를 건드리지 않는다."""
    out = _git("ls-tree", "-r", "--name-only", sha, cwd=CACHE / ns)
    dirs: dict[str, str] = {}
    for line in out.splitlines():
        if not line.endswith("/SKILL.md"):
            continue
        path = line[: -len("/SKILL.md")]
        parts = Path(path).parts
        if any(p in SKIP_PARTS for p in parts):
            continue
        dirs[parts[-1]] = path
    return dirs


def _desc_at(ns: str, sha: str, path: str) -> str:
    try:
        text = _git("show", f"{sha}:{path}/SKILL.md", cwd=CACHE / ns)
    except SourceError:
        return ""
    if m := _FRONTMATTER.match(text + "\n"):
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            return ""
        return " ".join(str(meta.get("description") or "").split())
    return ""


def compare(ns: str, old: str, new: str) -> dict:
    """두 커밋 사이에 스킬이 어떻게 달라졌는지.

    설명 변경을 본문 변경과 **따로** 센다. 설명은 매 세션 비용이고 본문은 아니다 —
    이 하네스가 재는 값이 정확히 그거라 섞으면 안 된다.
    """
    d = CACHE / ns
    old_dirs, new_dirs = _skill_dirs_at(ns, old), _skill_dirs_at(ns, new)
    changed = set(_git("diff", "--name-only", old, new, cwd=d).splitlines())

    added = [
        {"name": n, "tokens": len(_desc_at(ns, new, new_dirs[n])) // 4}
        for n in sorted(set(new_dirs) - set(old_dirs))
    ]
    removed = sorted(set(old_dirs) - set(new_dirs))

    modified = []
    for name in sorted(set(old_dirs) & set(new_dirs)):
        op, np = old_dirs[name], new_dirs[name]
        if not any(p.startswith(op + "/") or p.startswith(np + "/") for p in changed):
            continue
        od, nd = _desc_at(ns, old, op), _desc_at(ns, new, np)
        modified.append({
            "name": name,
            "desc_changed": od != nd,
            "old_tokens": len(od) // 4,
            "new_tokens": len(nd) // 4,
        })

    return {"added": added, "removed": removed, "modified": modified}
