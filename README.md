# harness2

단계(phase)별로 컨텍스트·권한·산출물 경로를 갈아끼우는 하네스.
Claude Code 기준으로 만들었고, 프로필 내용은 도구 중립이라 Codex·agy 로 확장 가능하다.

원칙과 그 출처는 [`PRINCIPLES.md`](PRINCIPLES.md) 에 있다. 실측 근거는
[`probe/results/phase0.md`](probe/results/phase0.md).

## 쓰는 법

```bash
hns list                    # 프로필 목록 (스킬·에이전트·MCP 개수 포함)
hns developer               # 현재 디렉터리를 프로젝트로 삼아 구현 단계 세션 시작
hns developer ~/work/proj   # 프로젝트 경로 지정
hns build [프로필]          # library/ + profile.yaml -> build/claude/<n>/
hns doctor [프로필]         # 규칙 검사 (Write deny 오용 등)
hns budget [프로필]         # 기동 토큰 실측 + 상한 대조 (모델 호출)
hns growth 0 10 25 50       # 스킬 개수 대비 비용 곡선 실측
hns golden [--update]       # 컴파일러 회귀 검사
hns argv developer          # 기동 인자만 출력 (실행하지 않음)
hns new <이름>              # 새 프로필
```

## 왜 미리 나누나

스킬 하나가 **매 세션 항상** 지는 비용을 실측했다 —
짧은 설명이면 ~70 토큰, 번들 스킬처럼 길면 ~161 토큰.
선형이다([`probe/results/growth.md`](probe/results/growth.md)).

| 라이브러리 총 스킬 | 안 나눴을 때 | 나눴을 때 (역할당 8개) |
|---:|---:|---:|
| 25 | +1.8k ~ +4.0k | +0.6k ~ +1.3k |
| 50 | +3.4k ~ +8.1k | +0.6k ~ +1.3k |
| 100 | +6.9k ~ +16.1k | +0.6k ~ +1.3k |

프로필 하나의 오버헤드는 **213 토큰** — 스킬 3개 값이다.
나누는 건 거의 공짜고, 안 나누면 선형으로 비싸진다.
그래서 라이브러리가 작을 때 미리 나눠 둔다.

**스킬 설명은 짧게 쓴다.** 본문은 호출 시에만 로드되지만 설명은 전원이 매번 낸다.

PATH 에 넣으려면:

```bash
echo 'export PATH="$HOME/Desktop/harness2/bin:$PATH"' >> ~/.zshrc
```

## 단계와 핸드오프

단계 사이는 대화가 아니라 **파일**로 넘어간다. 앞 단계 산출물은 다음 단계에서
**편집이 차단**되므로, 고쳐야 할 것 같으면 "앞 단계로 되돌릴 질문"으로 적힌다.

| 단계 | 읽는다 | 쓴다 |
|---|---|---|
| `researcher` | — | `docs/research/{slug}.md` |
| `pm` | research | `docs/prd/{slug}.md` |
| `designer` | prd | `docs/design/{slug}.md` |
| `developer` | design, prd (+review) | `src/**`, `tests/**`, `docs/decisions/{slug}.md` |
| `reviewer` | prd, design (+decisions) | `docs/review/{slug}.md` |

`hns doctor` 가 이 사슬이 끊겼는지 검사한다 — 아무도 안 만드는 문서를 기다리거나
아무도 안 읽는 문서를 만들면 알려준다.

### 쓰기 권한은 손으로 적지 않는다

각 단계의 `deny_write` 는 **모든 프로필의 `outputs` 에서 자동 유도**된다:

```
deny_write = (모든 프로필의 outputs) − (내 outputs)
```

그래서 프로필을 추가하면 **기존 프로필을 한 줄도 안 고쳐도** 나머지 전부가 새 산출물을
못 쓰게 된다. `profile.yaml` 의 `permissions.deny_write` 에는 **아무 프로필도 소유하지
않는 경로**만 적는다 (예: `.github/**`).

한계: 이건 denylist 다. 아무도 소유하지 않는 `README.md` 같은 파일은 누구나 쓸 수 있다.
목적이 **단계 경계 유지**이지 샌드박스가 아니라서 그렇게 뒀다.

## 전환

**전환은 새 프로세스에서만 성립한다.** 로드된 스킬과 권한은 세션 도중 되돌릴 수 없다.
세션 안에서 `/profile` 을 쓰면 완료 조건을 점검하고 다음 명령을 알려준다 —
전환하는 척하지 않는다.

```
> /profile designer
  ✓ developer 완료 조건: 3/4
  ⚠ 테스트 미실행
  다음: 이 세션을 닫고  hns designer
```

## 구조

```
PRINCIPLES.md          원칙 + 출처 + 강제 수단. 하네스의 헌법
core/                  전 프로필 공통 플러그인 (PREAMBLE.md, /profile 스킬)
library/               ★ 스킬·에이전트·MCP 정의가 한 벌만 사는 곳
  skills/<id>/SKILL.md
  agents/<id>.md
  mcp/<id>.json
profiles/<이름>/       ★ 도구 중립 단일 진실 원천
  profile.yaml         입출력·권한·스킬 id·MCP id·예산·완료 정의
  ROLE.md              단계 지시
adapters/claude/       Claude Code 문법을 아는 유일한 곳 (build.py, cli.py)
bin/hns                dispatch 만 한다
build/claude/<n>/      컴파일 산출물 = 실제 --plugin-dir 대상 (gitignore)
tests/golden/          컴파일러 회귀 기준
probe/results/         실측 결과
```

## 프로필 추가

**코드 변경 0.** 파일 2개만 고친다.

```bash
hns new researcher
# 1) profiles/researcher/profile.yaml  — inputs/outputs/deny/done_when
# 2) profiles/researcher/ROLE.md       — 순서·경계·자유도
hns doctor researcher
```

프로필을 늘리기 전에 자문할 것 — **지금 늘어난 것이 단계인가, 직함인가?**
직함이면 만들지 않는다 (`PRINCIPLES.md` 의 반론 절 참고).

## 격리가 뜻하는 것과 뜻하지 않는 것

**뜻한다** `[M]`
- 세션 프로세스에 core + 해당 프로필 플러그인만 들어간다. 다른 프로필의 스킬은
  읽히지도 토큰화되지도 않는다.
- 번들 스킬도 기본으로 끈다 (12개 → 1개, 약 1,776 토큰 절감).
- **MCP 도 선언한 것만 싣는다** — `--strict-mcp-config` 로 다른 모든 MCP 설정을 무시한다.
- 앞 단계 산출물은 `permissions.deny` 로 **실제 편집이 차단**된다.
- `~/.claude/settings.json` 에 아무것도 쓰지 않는다. 두 프로필을 다른 터미널에서
  동시에 띄워도 서로를 건드리지 않는다.

**뜻하지 않는다**
- 파일시스템 격리가 아니다. `Bash` 를 넓게 허용하면 deny 를 우회할 수 있다.
- 세션 도중 전환이 아니다. 전부 기동 시점에 결정된다.
- 전환하면 대화 맥락은 끊긴다. 그게 의도다 — 핸드오프는 문서로 한다.
