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

### Fixed

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
