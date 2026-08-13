# 검증 대기 — 등록했으면 잊어도 된다

`[?]` 를 문서 여기저기에 흩뿌리지 않고 여기에 모은다. 세션 시작 훅
(`bin/jig-pending-note`)이 이 파일을 보여주므로 **외울 필요가 없다.**

규칙:
- 항목은 `## ` 헤딩 하나 = 1건. **확인 방법 없이는 등록하지 않는다** — 확인 방법을
  적을 수 없으면 그것은 검증 대기가 아니라 그냥 모르는 것이다.
- 지금 하는 작업과 겹치거나 그 자리에서 잴 수 있으면 **지금 잰다.** 대개 잴 수 있다.
- 재면: 결과를 `probe/results/` 에 남기고, 근거가 걸린 문서의 `[?]` 를 갱신하고,
  항목을 **지운다.** 이 파일은 목록이지 기록이 아니다.
- 이 목록은 알림이지 강제가 아니다. 세션 목적을 밀어내면서까지 처리하지 않는다.

## /profile 이 done 필드를 실제로 state.json 에 쓰는가

- 왜: 기동 게이트가 이 기록에 의존한다. 스킬이 안 쓰면 게이트는 영원히 침묵한다
  (fail-open — 침묵이 곧 실패 모드).
- 확인: jig developer 세션에서 작업 후 `/profile reviewer` 실행 →
  `.harness/state.json` 에 `done: {passed, total, unmet}` 이 있는지 대조.
  결과는 `probe/results/launch-gate.md` 로.
- 등록: 2026-08-13

## SessionStart 훅이 resume · clear 에서도 주입되는가

- 왜: pending 표면화가 현재 `startup` 만 쓴다. 긴 세션의 요약(compact) 뒤나 재개
  세션에서 목록이 유실되는지에 따라 matcher 를 넓힐지 정한다.
- 확인: `probe/session-start/run.sh` 의 settings 에서 matcher 만 바꿔 재실행.
- 등록: 2026-08-13

## MCP 서버 1개의 세션 시작 비용

- 왜: 프로필이 MCP 를 선언하기 시작하면 budget 상한에 넣어야 하는데 계수가 없다.
- 확인: 로컬 stdio 에코 서버를 `library/mcp/` 에 선언한 프로필로 `jig budget` 전후
  대조. `-p` 경로에 앱 커넥터가 안 붙는 문제는 stdio 서버로 우회된다.
  (growth.md 의 `[?]` 에서 이관)
- 등록: 2026-08-13

## --agent <name> 이 --plugin-dir 로 들어온 에이전트를 이름으로 잡는가

- 왜: 프로필 기동 시 서브에이전트를 지정 기동할 수 있으면 agents 항목의 쓸모가 커진다.
- 확인: `claude --plugin-dir <빌드> --agent <name> -p "역할을 한 줄로"` —
  네임스페이스형(`<plugin>:<agent>`)도 시도. (phase0 에서 이관)
- 등록: 2026-08-13

## Stop 훅의 {"decision":"block"} 이 실제로 턴 종료를 막는가

- 왜: 성립하면 done_when 미충족 시 턴을 끝내지 못하게 하는, 기동 게이트보다 이른
  강제 지점이 생긴다.
- 확인: 최소 Stop 훅 + `-p` 실행. (phase0 에서 이관)
- 등록: 2026-08-13

## --resume <id> --plugin-dir <B> 가 재개 세션에 B 의 플러그인을 적용하는가

- 왜: 성공하면 "맥락 연속성은 포기한다" 는 현재 전환 설계의 전제가 바뀐다 —
  맥락 유지 프로필 전환이 가능해진다.
- 확인: 세션 ID 고정 후 플러그인만 바꿔 2회 실행 대조. (phase0 에서 이관)
- 등록: 2026-08-13

## claude plugin details 가 경로를 받는가

- 왜: 받으면 `jig budget` 의 토큰 예산 검사를 모델 호출(쿼터) 없이 할 수 있다.
- 확인: `claude plugin details <build/claude/<name> 경로>`. (phase0 에서 이관)
- 등록: 2026-08-13

## plugin eval --ablation with-without 이 경로 타겟에서 동작하는가

- 왜: 동작하면 스킬 유무 비교(ablation)를 프로필 eval 에 그대로 쓸 수 있다.
- 확인: `--help` 상 경로 타겟 기본값이 `none` 이므로 명시 지정해 실행. (phase0 에서 이관)
- 등록: 2026-08-13
