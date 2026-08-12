# 스킬 사용 기록 실측 결과

- 대상: Claude Code, macOS (Darwin 24.6.0)
- 일시: 2026-08-12
- 방법: `probe/skill-usage/run.sh` — 스킬 하나짜리 플러그인에 `matcher: "*"` 훅을 걸고
  `claude -p` 로 스킬을 부르게 한 뒤 훅이 받은 stdin 페이로드를 그대로 적었다.
- 재현: `bash probe/skill-usage/run.sh`

`jig usage` 설계 전체가 "훅으로 스킬 호출을 잡을 수 있는가"에 걸려 있었다. 세 질문에
전부 `[M]` 로 답이 나왔다.

## 결과

| # | 질문 | 판정 | 근거 |
|---|---|---|---|
| 1 | 스킬 호출에 `PreToolUse` 가 발화하는가 | **발화한다** | 아래 페이로드. `PostToolUse` 도 함께 발화한다 |
| 2 | `matcher` 에 무엇을 써야 잡히는가 | **`tool_name` 은 `Skill`** | `"*"` 로 전부 잡아 확인. 실제 설정에는 `"Skill"` 을 쓴다 |
| 3 | 어떤 스킬인지 식별되는가 | **`tool_input.skill`** | `"probeusage:probe-echo"` — `<플러그인>:<스킬>` 형식 |
| 4 | 스킬 정체성은 디렉터리명인가 frontmatter `name` 인가 | **디렉터리명** | 디렉터리를 `zzz-renamed-dir` 로 바꾸고 frontmatter 는 `name: probe-echo` 로 두자 훅이 `probeusage:zzz-renamed-dir` 로 보고 |

### `PreToolUse` 페이로드 (실제 수신값)

```json
{"session_id":"832dfdfb-…","transcript_path":"/Users/…/832dfdfb-….jsonl",
 "cwd":"/Users/bysu/workspace/jigkit","permission_mode":"acceptEdits",
 "hook_event_name":"PreToolUse","tool_name":"Skill",
 "tool_input":{"skill":"probeusage:probe-echo"},"tool_use_id":"toolu_01V1…"}
```

`PostToolUse` 는 여기에 `tool_response":{"success":true,…}` 와 `duration_ms` 가 붙는다.

## 설계에 직접 반영되는 것

### `[M]` 통계는 `PreToolUse` + `matcher: "Skill"` 로 모은다

트랜스크립트(`~/.claude/projects/**/*.jsonl`) 파싱이라는 후퇴안은 필요 없어졌다.
훅은 공식 인터페이스이므로 포맷이 임의로 깨지지 않는다.

`cwd` 가 페이로드에 있으므로 훅 스크립트는 **기록할 프로젝트를 스스로 안다.**
`session_id` 가 있으므로 세션 수도 셀 수 있다 — "몇 세션 중 몇 번 불렸나" 가 계산된다.

### `[M]` 스킬 정체성은 디렉터리 이름이다. frontmatter `name` 은 무시된다

4번의 결과로 두 가지가 정해졌다.

1. **빌드 출력에서 스킬 디렉터리를 평탄화하는 것으로 이름 충돌이 완전히 해결된다.**
   `anthropic/pdf` → `skills/anthropic-pdf/` 로 쓰면 두 소스가 같은 이름의 스킬을 가져도
   부딪히지 않는다. 상류 파일을 고칠 필요가 없다.
2. 계획에 있던 "frontmatter `name` 이 겹치면 `jig doctor` 가 FAIL" 검사는 **불필요하다.**
   겹쳐도 아무 일도 일어나지 않는다. 넣지 않는다.

훅이 보고하는 `<프로필>:<디렉터리>` 를 원래 스킬 id 로 되돌리는 것은 빌드 산출물의
`manifest.json` 이 맡는다 (`dir` → `id` 매핑).

플러그인 이름은 프로필 이름과 같으므로(`compile_profile` 이 `plugin.json` 에
`"name": <프로필>` 을 쓴다) `tool_input.skill` 앞부분이 곧 프로필이다.

## 남은 `[?]`

| 질문 | 확인 방법 |
|---|---|
| 훅 스크립트가 느리면 세션이 얼마나 지연되는가 | 페이로드에 `duration_ms: 3` 이 찍혔다. append 한 줄이면 무시할 수준이나, 훅이 실패할 때 세션이 막히는지는 별도 확인 필요 — 훅에서 의도적으로 `exit 1` 을 내고 대조 |
| 여러 플러그인(core + 프로필)이 붙었을 때 core 스킬 호출도 같은 형식인가 | `jig-core:profile` 호출을 한 번 발생시켜 로그 확인 |
