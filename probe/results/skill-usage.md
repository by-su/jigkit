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

## 훅 실패가 스킬 호출을 막는가 `[M]`

- 방법: `probe/skill-usage/run-failure.sh` — 훅을 `exit 1` / `exit 2` 로 각각 걸고
  스킬이 실행되는지 대조
- 재현: `bash probe/skill-usage/run-failure.sh`

| 훅 종료 코드 | 스킬 | 모델이 본 것 |
|---:|---|---|
| `1` | **실행됨** | 아무 일도 없다. 훅 실패가 무시된다 |
| `2` | **차단됨** | `PreToolUse:Skill hook error: …` 와 훅의 stderr 가 전달된다 |

**`2` 만 차단한다.** 다른 0 아닌 값은 비차단 오류다.

이 하네스에 주는 결론: `bin/jig-log-skill` 은 항상 `exit 0` 이고, 설령 그 보장이
깨지더라도 안전하다 — 파이썬 미처리 예외는 `1`, 실행 불가·인터프리터 없음은 `126`/`127`
이라 전부 비차단이다. **`2` 는 이 스크립트 어디에도 없다.** 즉 기록 훅이 깨져도
작업이 막히는 일은 구조적으로 일어나지 않는다.

(뒤집어 말하면 `exit 2` 는 스킬을 **막는 데 쓸 수 있는** 지렛대다. 프로필별로 특정
스킬을 차단하고 싶어지면 여기가 그 자리다. 지금은 쓰지 않는다.)

## core 플러그인 스킬도 같은 형식으로 잡히는가 `[M]`

`--plugin-dir core` 와 `--plugin-dir build/claude/developer` 를 함께 붙인 실제 기동
구성에서 core 의 `/profile` 스킬을 호출했다.

```json
{"ts": "…", "session": "341157bd-…", "plugin": "jig-core", "dir": "profile"}
```

형식이 같다. 그리고 더 중요한 것 — **프로필 플러그인에 심은 훅이 다른 플러그인의 스킬
호출까지 잡는다.** 훅은 플러그인 경계가 아니라 세션 단위로 걸린다. 세션당 훅 하나로
전부 커버되므로 core 에 훅을 따로 심을 필요가 없다.

`jig usage` 는 플러그인 이름이 프로필 이름과 일치할 때만 그 프로필로 집계하고,
나머지는 `(프로필 외 호출: jig-core)` 로 따로 보여준다.

## 느린 훅은 세션을 얼마나 붙잡는가 `[M]`

실질 질문은 "얼마나 느려지나" 가 아니라 **"위험을 묶을 수 있나"** 다.

- 방법: `probe/skill-usage/run-latency.sh` — 같은 프롬프트로 세 구성의 벽시계 시간 비교
- 재현: `bash probe/skill-usage/run-latency.sh`

| 구성 | 벽시계 | 스킬 |
|---|---:|---|
| 즉시 끝나는 훅 (기준선) | 8초 | 실행됨 |
| `sleep 8` | 17초 | 실행됨 |
| `sleep 8` + `"timeout": 2` | 9초 | 실행됨 |

**훅은 동기적으로 막는다.** `sleep 8` 이 그대로 +8초로 나타났다 — 훅의 소요 시간이
**스킬 호출마다** 더해진다. 그리고 **`timeout` 이 실제로 상한을 건다.** 타임아웃된
훅은 스킬을 막지 않는다(세 번째 줄에서도 스킬이 실행됐다).

### 설계에 반영한 것 — 생성되는 훅에 `"timeout": 5`

`bin/jig-log-skill` 은 한 줄 append 라 평시에는 밀리초다(페이로드의 `duration_ms: 3`).
문제는 평시가 아니라 디스크가 차거나 NFS 가 멎는 경우다 — 지연이 동기적이라는 것이
측정으로 확인된 이상, **그때 모든 스킬 호출이 함께 멎는다.** 상한이 걸려 있으면
최악이 스킬당 5초이고, 그마저도 스킬은 정상 실행된다.

한 필드로 폭발 반경을 묶는 것이라 P10 과 결이 같다.
