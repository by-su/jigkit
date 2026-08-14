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

## 플러그인이 배달하는 SessionStart 훅이 실제로 발화하는가

- 왜: 검증 대기 주입의 jig 세션 쪽 절반이 이 배선(build.py 의 hooks.json)에 걸려
  있다. 실측(session-start.md)은 settings 경로만 쟀다 — 플러그인 경로가 안
  발화하면 jig 세션에서 목록이 조용히 사라진다 (fail-silent).
- 확인: `probe/session-start/run.sh` 를 복제해 훅을 settings 대신 `--plugin-dir`
  플러그인의 hooks/hooks.json 으로 배달하고 `-p` 실행 stdout 대조.
  결과는 `probe/results/session-start.md` 에 추가.
- 등록: 2026-08-13

## --setting-sources user 가 프로젝트 settings 훅을 정말 배제하는가

- 왜: "이중 훅 배선이 겹쳐 발화하지 않는다" 는 README 주장의 유일한 근거인데
  미실측이다. 배제되지 않으면 체크아웃 안의 jig 세션이 pending-note·commit-gate
  를 이중 발화한다.
- 확인: 이 체크아웃에서 `jig argv <프로필>` 의 argv 로 `-p` 실행하되
  `.claude/settings.json` 훅에 마커 stdout 을 넣어 이중 출력 여부 대조.
  결과는 `probe/results/session-start.md` 에 추가.
- 등록: 2026-08-13

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

## Logfire MCP 서버의 실행 인자

- 왜: `python.yaml` 의 `logfire` 항목이 `why` 에서 `[?]` 로 이 파일을 가리키는데
  등록된 적이 없다 — 가리키는 곳이 비어 있으면 `[?]` 가 그냥 사라진 것과 같다.
- 확인: pydantic/logfire-mcp 의 README 에서 설정 JSON 을 읽고, 그 패키지가 실제로
  배포돼 있는지 `curl -s -o /dev/null -w '%{http_code}' https://registry.npmjs.org/<이름>`
  로 대조한다. 없으면 항목을 `surface: library` 로 내린다 — 없는 표면을 있다고 적어
  두면 켰을 때 기동에 실패한다 (vitest 가 그랬다).
- 등록: 2026-08-14

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
