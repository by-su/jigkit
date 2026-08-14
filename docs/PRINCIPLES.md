# 하네스 원칙

이 문서가 jigkit 의 헌법이다. 프로필·런처·훅은 전부 여기서 정당화된다.

원칙마다 네 칸을 갖는다 — **정의 / 출처 / 강제 수단 / 등급**.
`강제 수단` 이 "프롬프트"뿐인 원칙은 **약한 원칙**이다. 약한 채로 오래 남은 원칙은
원칙이 아니라 취향이므로 지운다.

## 근거 등급 표기 규칙

주장에는 등급을 붙인다. 강한 것부터:

| 등급 | 뜻 |
|---|---|
| `[S]` | 소스코드 — 최종 권위 |
| `[D]` | 공식 문서 |
| `[D-3rd]` | 3rd-party 지식베이스 |
| `[M]` | 직접 실측 |
| `[O]` | 관찰된 동작 (이슈 리포트 포함) |
| `[J]` | 내 판단 |
| `[?]` | 불확실 |

**충돌하면 강한 쪽을 택하고, 충돌했다는 사실과 어느 쪽을 택했는지 함께 적는다.**
`[?]` 항목마다 **무엇을 어떻게 확인하면 답이 나오는지**를 붙인다.
`[?]` 에 핵심 기능을 걸지 않는다.

---

## 원칙

### P01 · 가장 단순한 것부터. 에이전트성은 값을 치르고 늘린다

프레임워크나 다중 에이전트를 먼저 놓지 않는다. 단순한 구성이 **실패하는 것을 보고 나서**
복잡도를 늘린다.

- 출처: Anthropic, *Building Effective Agents* — "add multi-step agentic systems only when
  simpler solutions fall short" / OpenAI, *A practical guide to building agents* —
  "maximize a single agent's capabilities first"
- 강제: 빌드 순서가 마일스톤 1(프로필 1개)에서 멈춰도 쓸 수 있게 설계한다. `bin/jig` 는
  dispatch 만 한다.
- 등급: `[D]`

### P02 · 컨텍스트는 유한하고, 채울수록 성능이 나빠진다

토큰을 "채우는" 게 아니라 "쓰는" 것으로 다룬다.

- 출처: Claude Code best practices — "performance degrades as it fills" /
  Anthropic, *Effective context engineering* — "the smallest set of high-signal tokens" /
  Chroma, *Context Rot* (18개 모델 실측) — "model performance varies significantly as input
  length changes, even on simple tasks"
- 강제: 프로필마다 토큰 예산 상한. `jig doctor` 가 스킬 설명 + 시스템 프롬프트 크기를 재고
  넘으면 실패한다.
- 등급: `[D]` + `[M]`(Chroma 는 3자 실측)

### P03 · 점진적 공개 — 색인만 올리고 본문은 필요할 때

- 출처: Anthropic, *Agent Skills* — "skills let Claude load information only as needed" /
  *Code execution with MCP* — 150k → 2k 토큰(98.7% 절감)
- 강제: **기동 시 프로필 플러그인 하나만 붙인다.** 스킬 본문은 호출 시에만 로드된다.
  긴 참조는 `references/` 로 내리고 SKILL.md 에서 한 단계만 링크한다.
- 등급: `[D]` + `[M]`(probe #3·#4·#5)

### P04 · 지시는 적정 고도로 쓰고 무자비하게 쳐낸다

브리틀한 하드코딩도, 공허한 일반론도 아닌 중간.

- 출처: Claude Code best practices — "Bloated CLAUDE.md files cause Claude to ignore your
  actual instructions" / Anthropic, *Effective context engineering* — 실패 모드는
  "hardcoding complex, brittle logic" 와 "vague, high-level guidance" 양쪽
- 강제: `core/PREAMBLE.md` 줄 수 상한을 `jig doctor` 가 검사. 모든 줄은
  **"지우면 실수가 늘어나나?"** 를 통과해야 한다.
- 등급: `[D]`

### P05 · 자유도는 작업의 취약성에 맞춘다

여러 길이 통하는 곳엔 방향만, 한 번 틀리면 끝인 곳엔 절차를.

- 출처: Anthropic, *Skill authoring best practices* — "narrow bridge with cliffs on both
  sides" vs "open field with no hazards"
- 강제: 각 `BRIEF.md` 가 자유도를 명시한다. 되돌리기 어려운 단계만 순서를 못 박는다.
- 등급: `[D]`

### P06 · 에이전트가 스스로 돌릴 수 있는 검사를 준다

이 하네스에서 가장 값이 큰 장치다. 검사가 없으면 사람이 검증 루프가 된다.

- 출처: Claude Code best practices — "Without a check it can run, 'looks done' is the only
  signal available, and you become the verification loop" / Anthropic Agent SDK —
  최선의 피드백은 "clearly defined rules for an output"
- 강제: `profile.yaml:done_when` 은 가능한 한 **실행 가능한 명령**으로 적는다.
- 등급: `[D]`

### P07 · 반드시 지켜야 할 것은 권한·훅으로, 안내만 프롬프트로

- 출처: Claude Code best practices — "Unlike CLAUDE.md instructions which are advisory,
  hooks are deterministic" / OpenAI — 계층형 가드레일, "a single one is unlikely to provide
  sufficient protection"
- 강제: 역할별 `permissions.deny`. **deny 규칙은 `Edit(...)` 로 쓴다** — `Write(...)` 는
  파일 권한 검사에 걸리지 않는다 `[M]` (probe #8, CLI 가 직접 경고).
- 등급: `[D]` + `[M]`

### P08 · 단계를 나누고 산출물 **파일**로 넘긴다

맥락을 넘기지 말고 문서를 넘긴다. 이 코퍼스에서 가장 여러 곳이 독립적으로 합의한 원칙이다.

- 출처: HumanLayer *ACE-FCA* — Research→Plan→Implement, "each producing a compacted artifact
  that serves as the input for the next phase" / Anthropic, *Effective harnesses for
  long-running agents* — 각 세션은 "no memory of what came before" 에서 시작하므로
  진행 파일·git 로그·기능 목록으로 이어붙인다
- 강제: 핸드오프 규약 표. 각 역할은 앞 단계 문서만 읽고 시작하며, 앞 단계 문서는
  deny 로 **편집이 차단**된다.
- 등급: `[D]`

### P09 · 상태는 파일에. 세션과 하네스는 버려도 되는 것

- 출처: Anthropic, *Scaling Managed Agents* — 하네스는 "cattle, not pets" /
  12-Factor Agents — stateless reducer, 컨텍스트 창을 직접 소유하라
- 강제: `.harness/state.json` + `docs/` 산출물이 유일한 진실. 세션은 언제 끊겨도 된다.
  쓰기 경로마다 **되읽기 검사**를 짝짓는다.
- 등급: `[D]`

### P10 · 역할마다 도구·권한을 좁히고 폭발 반경을 묶는다

- 출처: Anthropic, *subagents* 문서 — `tools` 허용목록으로 "Enforce constraints" /
  OpenAI — 도구마다 읽기/쓰기·되돌림 가능성·금전 영향으로 위험 등급을 매겨라 /
  Simon Willison, *Designing agentic loops* — 샌드박스·범위 제한 자격증명으로 폭발 반경을 묶어라
- 강제: `--settings` 의 프로필별 deny + `--setting-sources user` 로 프로젝트 설정이
  프로필 권한을 덮지 못하게 한다 `[M]`.
  - 이 플래그는 **프로젝트 `CLAUDE.md` 자동 발견까지 함께 끈다** `[M]`
    (probe/results/memory-files.md). 좁히기의 대가로 프로젝트 지침이 조용히
    빠지므로, 컴파일러가 그 내용을 시스템 프롬프트에 편입한다 — 배선은 배제한 채
    내용만 가져오는 것이다.
  - 그 편입은 **폭발 반경을 한 뼘 넓힌다**: 프로젝트 저장소의 텍스트가 시스템
    프롬프트로 들어온다. 권한은 프로필의 것이 그대로 서지만 행동 지침은 그렇지
    않으므로, 신뢰하지 않는 저장소에서 프로필을 띄우는 것은 이 원칙이 막아 주지
    않는다. 알고 지불하는 대가다 `[J]`.
- 등급: `[D]`

### P11 · 사람은 diff 가 아니라 **계획**에서 검토한다

- 출처: HumanLayer — "A bad line of code is… a bad line of code. But a bad line of a plan
  could lead to hundreds of bad lines."
- 강제: PM·디자이너 산출물이 사람 검토 지점이다. 개발자 프로필은 **승인된 문서에서만**
  시작한다(선행 산출물 없으면 기동 시 경고).
- 등급: `[D-3rd]` (실무자 글)

### P12 · 하네스 자체를 평가하고, 가정을 주기적으로 의심한다

- 출처: Hamel Husain, *Your AI Product Needs Evals* — 실패한 제품의 공통 원인은
  "a failure to create robust evaluation systems" /
  Anthropic, *Skill authoring* — "**Create evaluations BEFORE writing extensive
  documentation.**" /
  Anthropic, *Scaling Managed Agents* — 하네스의 가정은 "can go stale as models improve"
- 강제: 프로필당 eval 3개 이상. 발견한 문제는 문서 항목이 아니라 **eval 케이스**로 적는다.
  원칙표는 6개월마다 재검토한다.
- 등급: `[D]`

---

## 충돌하는 지점 — 평균내지 않고 병기한다

### 멀티에이전트 찬반

- **찬성**: Anthropic 은 orchestrator-worker 구조가 단일 에이전트 대비 **+90.2%** 라고
  보고했다(*Multi-agent research system*). 서브에이전트는 별도 컨텍스트 창에서 돌고
  요약만 돌려준다.
- **반대**: Cognition, *Don't Build Multi-Agents* — "Actions carry implicit decisions, and
  conflicting decisions carry bad results." 단일 스레드 선형 에이전트를 권한다.
- **양쪽이 실제로 합의하는 선**: Anthropic 자신도 "Most coding tasks involve fewer truly
  parallelizable tasks than research" 라고 적었고, Cognition 의 2026 후속 글은
  "writes stay single-threaded" 로 좁혔다.
  → **읽기는 병렬로, 쓰기는 단일 스레드로.** 이 하네스는 그 선을 따른다.

### 실패 기록을 남길 것인가

- **남긴다**: Manus — "leave the wrong turns in the context". 실패가 모델에 증거를 준다.
- **걷어낸다**: Armin Ronacher, Claude Code 문서 — 실패 트랜스크립트는 모델을 막다른 길에
  고정시킨다. "같은 문제로 두 번 넘게 교정했다면 `/clear`."
- **합의점**: 원본 트랜스크립트 대신 **무엇을 시도해 왜 실패했는지의 압축 기록**을 남긴다.
  이 하네스에서는 그 기록이 `docs/decisions/` 에 간다.

---

## 이 설계에 대한 반론 — 지우지 않고 남긴다

Shrivu Shankar 는 커스텀 서브에이전트를 **"a brittle solution"** 이라 부르며
**"They Gatekeep Context"** 를 지적한다 — 역할을 나누면 그 역할이 쥔 맥락이 나머지에서
숨겨진다. 같은 저자는 "specialists have cross-dependencies that the lead fails to provide"
를 실패 모드로 명명한다.

1차 소스를 정직하게 읽으면 이렇다. **근거가 탄탄한 분리는 "직함(persona)" 이 아니라
"단계(phase)와 컨텍스트 경제성" 에 의한 분리다.** 분리를 옹호하는 어떤 1차 소스도
*직함 자체가 품질을 올린다*고 주장하지 않는다. 전부 컨텍스트 격리·신선도·비용으로
정당화한다.

그래서 이 하네스의 프로필은 **역할 연기가 아니라 단계 스코프**다.
`profile.yaml` 은 "너는 디자이너다" 가 아니라 **무엇을 읽고(inputs) · 무엇을 쓸 수 있고
(outputs) · 무엇을 쓰면 안 되는지(deny)** 로 역할을 규정한다.
`BRIEF.md` 도 정체성이 아니라 그 단계의 판단 기준과 완료 조건을 쓴다.

**프로필을 추가할 때 자문할 것**: 지금 늘어난 것이 *단계*인가, 아니면 *직함*인가?
직함이면 만들지 않는다.
