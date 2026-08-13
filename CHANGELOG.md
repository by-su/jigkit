# Changelog

사람용 변경 이력이다. 에이전트는 현재 상태를 서술하는 README·BRIEF 를 읽는다 —
이 파일은 "언제 무엇이 바뀌었는가" 를 사람이 되짚을 때 본다.

작성 규칙:

- **사용자에게 보이는 변경만** 기록한다. 리팩터링·테스트·내부 정리는 쓰지 않는다 —
  전부 쌓으면 아무도 안 읽는 소음 파일이 된다.
- 새 변경은 `[Unreleased]` 에 쌓는다. 분류는 Keep a Changelog 의 여섯 가지
  (Added / Changed / Deprecated / Removed / Fixed / Security), 빈 분류는 생략한다.
- 항목은 한 줄: `**제목**: 요약 (\`핵심 파일 경로\`)`.
- 버전 끊기는 사람이 한다 — `[Unreleased]` 를 `[x.y.z] - 날짜` 로 개명하고
  새 `[Unreleased]` 를 위에 만든다. 에이전트는 버전을 만들지 않는다.
- 이 파일은 커밋 게이트의 primary 문서가 아니다. **이 파일만 stage 해도
  문서 게이트를 통과하지 못한다** — 이력은 "문서를 봤다" 의 증거가 아니다.

## [Unreleased]

### Added

- **스택 카탈로그**: 언어·기능별로 어떤 도구를 **어떤 표면**(MCP · agents · 훅 · 게이트 ·
  설치만)으로 붙이는지를 `library/stacks/*.yaml` 한 곳에 두고, 카탈로그 문서와 배치 절차를
  거기서 생성한다 (`library/stacks/README.md`)
- **`jig stack`**: `list` · `show [--with] [--plan]` · `apply [--apply]` · `check`.
  `apply` 는 훅 디스패처·설정 파일·MCP 정의를 배치하고 기본은 dry-run 이다
  (`adapters/stacks.py`, `adapters/claude/stack_apply.py`)
- **프리셋과 alias**: `api`(FastAPI) · `web-app`(Next.js) · `nest-api` · `mobile` · `ui-lib`.
  "fastapi 로 백엔드 만들어줘" 가 추론이 아니라 조회로 풀린다 (`library/stacks/presets.yaml`)
- **`stack` 스킬**: 프로젝트 생성·스택 추가 요청에서 발동해 조합을 조회하고 `--plan` 을
  실행한 뒤 `check` 로 대조한다. developer 프로필에 켜져 있다
  (`library/skills/stack/SKILL.md`)
- **분기 은퇴**: 카탈로그에서 항목을 지우면 이미 적용된 프로젝트의 훅 분기도 다음 `apply` 에
  사라지고, 무엇을 지웠는지 출력한다. 다른 스택이 쓰는 분기는 카탈로그 정의로 다시 렌더해
  유지한다. `jig stack check` 는 apply 없이도 남아 있는 분기를 짚는다
  (`adapters/claude/stack_apply.py`)
- **프로필 컴파일러와 런처**: `profile.yaml` + `BRIEF.md` 를 `build/claude/<name>/` 의
  실제 Claude Code 플러그인(설정·MCP 설정·시스템 프롬프트 포함)으로 컴파일하고,
  `--plugin-dir` 로 띄워 `~/.claude` 에는 아무것도 쓰지 않는다. 컨텍스트는 기동 시점에
  여섯 축(스킬·MCP·서브에이전트·내장 도구·권한·로드되는 설정 층)으로 좁힌다
  (`adapters/claude/build.py`, `adapters/claude/cli.py`)
- **첫 명령 표면**: `jig <profile>` · `list` · `build` · `doctor` · `budget` · `growth` ·
  `golden` · `argv` · `new` (`bin/jig`)
- **다섯 단계 프로필**: researcher · pm · designer · developer · reviewer — 각자 무엇을
  읽고 무엇을 쓰고 언제 끝나는지 선언한다 (`profiles/`)
- **쓰기 권한 유도**: 프로필은 다른 모든 프로필의 산출물이 자동으로 deny 된다 — 손으로
  유지하던 목록에 이미 나 있던 구멍 세 개를 닫고, 여섯 번째 프로필이 나머지 다섯에
  파일 수정 없이 전파된다 (`adapters/claude/build.py`)
- **MIT 라이선스** (`LICENSE`)
- **영문 README 정본과 한국어 번역**: 절 구조를 1:1 로 맞춘다
  (`README.md`, `README.ko.md`)
- **오픈소스 스킬 소스**: `jig source add/list` · `jig sync [--check|--update]` ·
  `jig skills` — repo URL 과 고정 SHA 만 커밋하고 내용은 `library/cache/<ns>/` 로 받는다.
  상류 변경이 벤더링된 사본이 아니라 SHA 한 줄 diff 로 리뷰를 통과한다
  (`adapters/sources.py`, `library/sources.yaml`)
- **스킬 사용 기록**: 프로필 플러그인에 심은 PreToolUse 훅이 실제로 호출된 스킬을 남기고
  `jig usage` 가 프로필별로 "호출된 것 대 선언된 것" 을 보여준다 — 숫자만 보여주고
  자동으로 지우지 않는다 (`bin/jig-log-skill`)
- **기록 훅의 5초 상한**: 훅 지연이 스킬 호출마다 동기적으로 더해지는 것을 재고
  생성되는 `hooks.json` 에 `timeout: 5` 를 넣었다 — 디스크가 차거나 NFS 가 멎어도
  최악이 스킬당 5초이고 스킬은 그래도 실행된다 (`adapters/claude/build.py`)
- **`bootstrap.sh` 첫 실행 셋업**: 프리플라이트 → `jig sync` → `jig doctor` → PATH 안내
  순서로 돌고 재실행해도 안전하다. rc 파일은 `--path` 를 줬을 때만 건드린다
  (`bootstrap.sh`)
- **문서 영향 게이트**: 코드가 바뀌었는데 staged 에 `.md` 가 하나도 없으면 커밋을 막고,
  어떤 primary 문서가 그 변경을 언급하는지 짚어 준다 — 문서가 맞는지는 판정하지 않는다.
  `jig touched [range]` 로 따로도 보고, 우회는 `JIG_TOUCHED_BYPASS=1`
  (`bin/jig-commit-gate`, `adapters/touched.py`)
- **명령 블록 생성**: `jig --help` 와 두 README 의 명령 목록을 표 하나에서 만든다 —
  `jig docs --update` 로 재생성, `jig docs --check` 로 최신성 검사 (`adapters/commands.py`)
- **`jig selftest`**: 게이트·문서 라우팅의 회귀 검사를 명령으로 노출 (`tests/test_gate.py`)
- **기동 게이트**: 이전 단계가 done_when 미충족으로 끝났으면 전진 기동을 막는다 —
  판정 기록은 `/profile` 이 새로 쓸 때까지 기동 사이에 이월된다 (`adapters/launchgate.py`)
- **검증 대기 주입**: `probe/PENDING.md` 를 세션 시작 때 컨텍스트에 주입한다
  (`bin/jig-pending-note`)
- **CHANGELOG 도입**: 사람용 변경 이력과 작성 규칙 (`CHANGELOG.md`)
- **새 CLI 표면 게이트**: 새 명령·플래그가 어떤 primary 문서에도 없으면 커밋을
  막는다 — 미문서화 기능이 조용히 통과하던 구멍을 닫음 (`bin/jig-commit-gate`,
  `adapters/touched.py`)
- **selftest 확장**: 생성된 명령 블록의 최신성(`jig docs --check` 상당)과
  README.md ↔ README.ko.md 절 구조 1:1 을 `jig selftest` 가 검사 (`tests/test_gate.py`)

### Changed

- **명령 이름**: `hns` → `jig`, 코어 플러그인은 `jig-core` (스킬은 `jig-core:profile` 로
  namespace 된다) (`bin/jig`, `core/.claude-plugin/plugin.json`)
- **프로필 브리프 파일**: `ROLE.md` → `BRIEF.md` — 이 저장소가 "직함이 아니다" 라고
  주장하는 것에 파일 이름을 맞췄다 (`profiles/*/BRIEF.md`)
- **사용 기록의 단위**: 프로젝트별 → 전역 `~/.jigkit/skill-usage.jsonl` 한 곳으로 모은다.
  레코드에 `project` 를 남겨 `jig usage --project <경로>` 로 좁히고, `JIG_USAGE_LOG` 로
  경로를 덮을 수 있다 (`bin/jig-log-skill`, `adapters/claude/cli.py`)

### Fixed

- **커밋 게이트 트리거 누락**: `git commit` 문자열 포함 검사라 `git -c user.name=x commit`,
  `git --no-pager commit`, `git -C "/path with space" commit` 을 전부 놓치던 문제 —
  토큰화 한 번으로 판정한다 (`bin/jig-commit-gate`)
- **게이트 감시 범위**: adapters·bin·bootstrap.sh 만 봐서 profiles·core·library 변경이
  문서와 어긋나도 못 보던 문제와, `docs/decisions/{slug}.md` 형태의 경로가 토큰으로
  안 나오던 문제 (`bin/jig-commit-gate`, `adapters/touched.py`)
- **우회 오인**: 커밋 메시지에 `JIG_TOUCHED_BYPASS` 를 언급만 해도, 또 뒤에 붙은 env
  대입만으로도 게이트가 꺼지던 문제 — `git` 토큰 바로 앞의 대입이고 명령 안의 모든
  `git commit` 이 우회를 달았을 때만 인정한다 (`bin/jig-commit-gate`)
- **따옴표 안의 operator**: `git commit -m "docs: A && B"` 처럼 메시지에 `&&`·`;`·`#` 가
  있으면 명시적 우회가 거절되던 문제 (`bin/jig-commit-gate`)
- **설치 안내의 경로 하드코딩**: `~/jigkit` 이 박혀 있어 다른 위치로 클론하면 PATH 가
  조용히 어긋나던 문제 — 어디에 클론하든 `./bootstrap.sh` 한 번이다
  (`README.md`, `README.ko.md`)
- **`jig docs` 의 마커 부재**: 생성 마커가 지워지면 트레이스백이 새던 문제 — 무엇을
  되살려야 하는지 말한다 (`adapters/commands.py`)
- **커밋 게이트의 -a 우회**: `git commit -a`·pathspec 커밋이 index 만 보는 훅을
  그대로 지나가던 문제 — 그 형태는 추적 중인 작업트리 기준으로 판정한다
  (`bin/jig-commit-gate`, `adapters/touched.py`)
- **기동 게이트의 과차단**: 뒤로·옆으로의 이동까지 막던 문제 — 기록된 `next` 로의
  전진만 막는다. `passed: true` 같은 bool 기록을 유효로 오인해 완료된 단계를
  차단하던 문제도 함께 (`adapters/launchgate.py`)
- **오타 프로필에 우회 코칭**: 이름 검증이 기동 게이트보다 뒤라서, 존재하지 않는
  프로필에 차단 메시지와 우회 안내가 뜨던 문제 (`adapters/claude/cli.py`)
- **검증 대기 건수 부풀림**: 코드 펜스 안의 `## ` 를 항목으로 세던 문제
  (`bin/jig-pending-note`, `adapters/claude/cli.py`)
- **기동 게이트의 복구 망각**: 같은 프로필 재기동이 미충족 done_when 기록을 지워
  게이트가 무장해제되던 문제 — 새 판정이 쓰일 때까지 기록을 보존한다 (`adapters/claude/cli.py`)
- **기동 크래시**: `.harness/state.json` 의 인코딩이 깨지면 `jig <profile>` 이
  트레이스백으로 죽던 문제 — 이제 fail-open 계약대로 조용히 통과한다 (`adapters/claude/cli.py`)
- **차단 메시지 도배**: done_when 의 unmet 이 리스트 대신 문자열이면 글자 단위로
  출력되던 문제 (`adapters/launchgate.py`)
