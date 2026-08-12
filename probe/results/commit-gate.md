# 커밋 게이트 실측 결과

- 대상: Claude Code, macOS (Darwin 24.6.0)
- 일시: 2026-08-13
- 방법: `probe/commit-gate/run.sh` — `PreToolUse`/`matcher: "Bash"` 훅을 걸고
  (1) 페이로드를 적기만 하는 훅, (2) 특정 명령에만 `exit 2` 를 내는 훅으로 나눠 실행
- 재현: `bash probe/commit-gate/run.sh`

커밋 시점에 문서 영향을 **에이전트 컨텍스트로 강제 주입**하는 설계가 성립하는지가
두 가정에 걸려 있었다. 둘 다 참이다.

## 결과

| # | 질문 | 판정 | 근거 |
|---|---|---|---|
| 1 | `PreToolUse` 가 `Bash` 로도 발화하는가 | **발화한다** | 아래 페이로드 |
| 2 | 실행될 명령 문자열을 알 수 있는가 | **`tool_input.command`** | `"command":"echo PROBE_HELLO_2231"` |
| 3 | `exit 2` 가 Bash 명령을 막는가 | **막는다** | 명령이 실행되지 않았다 |
| 4 | 훅의 stderr 가 모델에게 가는가 | **원문 그대로 간다** | 모델이 마커를 인용했다 |

### `PreToolUse` 페이로드 (실제 수신값)

```json
{"session_id":"982f084a-…","transcript_path":"/Users/…/982f084a-….jsonl",
 "cwd":"/Users/bysu/workspace/jigkit","permission_mode":"acceptEdits",
 "hook_event_name":"PreToolUse","tool_name":"Bash",
 "tool_input":{"command":"echo PROBE_HELLO_2231","description":"Echo probe string"},
 "tool_use_id":"toolu_01GW…"}
```

### 차단 시 모델이 본 것

```
PreToolUse:Bash hook error: [.../block.sh]: PROBE_STDERR_MARKER_4417: 이 명령은 게이트가 막았다.
```

모델은 이어서 "훅이 막은 것이므로 **우회 시도 없이 여기서 멈췄습니다**" 라고 답했다.
차단이 조용히 무시되지 않고 응답해야 할 입력으로 다뤄진다는 뜻이다 `[O]`.

## 설계에 직접 반영되는 것

### `[M]` 게이트를 Claude 훅으로 만들 수 있다

세 조각이 다 갖춰졌다.

- `tool_input.command` → 실행될 명령이 `git commit` 인지 판별할 수 있다
- `cwd` → **jigkit 저장소 안에서만** 동작하도록 가드할 수 있다. 남의 프로젝트에서는
  즉시 `exit 0` 으로 빠진다
- `exit 2` + stderr → 문서 히트 목록을 에이전트에게 **강제로** 보여줄 수 있다.
  이것이 CLAUDE.md(advisory) 대신 훅을 쓰는 이유 전체다

### `[M]` 우회는 직접 설계해야 한다

`git commit --no-verify` 는 **git 훅 우회 옵션이지 Claude 훅 우회 옵션이 아니다.**
이 게이트에는 듣지 않는다. 대신 명령 문자열이 페이로드에 그대로 오므로
`JIG_TOUCHED_BYPASS=1 git commit …` 을 훅이 문자열로 알아볼 수 있다.

환경변수를 탈출구로 쓰는 이유는 **우회가 트랜스크립트에 흔적을 남기기 때문**이다.
에이전트가 그냥 넘어간 것이 나중에 보인다.

## 한계 — 과장하지 않는다

이 게이트는 **문서가 맞는지 판정하지 않는다.** "문서를 하나도 staged 하지 않았다" 만
본다. 엉뚱한 문서 한 줄만 staged 해도 통과한다.

- 막는 것: 코드를 바꾸고 **문서를 아예 안 보고** 지나가는 실패
- 못 막는 것: 문서를 봤는데 **잘못 고치거나 부족하게 고치는** 실패
