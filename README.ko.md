# jigkit

> 정본은 [README.md](README.md) (영어). 이 문서는 한국어 번역이다.

**AI 코딩 에이전트용 프로필 하네스.** 작업 단계마다 로드되는 스킬·MCP·도구·권한을
갈아끼워, 스킬 라이브러리가 커져도 세션이 무거워지지 않게 한다.

목공의 **지그(jig)** 에서 이름을 따왔다. 지그는 공구가 정해진 경로 밖으로 못 나가게
가두는 치구다 — 작업자의 숙련도와 무관하게 같은 결과가 나오게 하려고 존재한다.
이 저장소가 코딩 에이전트에 하는 일이 그것이다. 규칙은 프롬프트가 아니라 권한에 산다.

Claude Code 기준으로 만들었다. 프로필 내용은 도구 중립이라 다른 CLI 어댑터를 붙일 때
프로필을 다시 쓸 필요가 없다. MIT 라이선스.

## 라이브러리가 커지기 전에 나누는 이유

스킬의 **설명**은 쓰든 안 쓰든 매 세션 시작에 로드된다. 본문만 미뤄진다.
Claude Code 2.1.228 에서 실측했다 ([`probe/results/growth.md`](probe/results/growth.md)):

| 로드된 스킬 | 기동 토큰 | 스킬당 |
|---:|---:|---:|
| 0 | 12,069 | — |
| 10 | 12,815 | 75 |
| 25 | 13,820 | 70 |
| 50 | 15,495 | 69 |

선형이고, 설명이 짧으면 ~70 토큰, 길면 ~161 토큰이다. 프로필 하나의 비용은 213 토큰이다.
즉 나누는 건 사실상 공짜고, 안 나누면 선형으로 비싸진다:

| 라이브러리 크기 | 전부 로드 | 프로필별 (역할당 8개) |
|---:|---:|---:|
| 25 | +1.8k – 4.0k | +0.6k – 1.3k |
| 50 | +3.4k – 8.1k | +0.6k – 1.3k |
| 100 | +6.9k – 16.1k | +0.6k – 1.3k |

25개 아래면 별 차이 없다. 50개를 넘으면 갈린다. 나누기 싼 시점은 거기 도달하기 전이다.

**스킬 설명은 짧게 쓴다.** 본문은 호출할 때만 로드되지만, 설명은 매 세션이 매번 낸다.

## 설치

```bash
git clone https://github.com/by-su/jigkit ~/jigkit
echo 'export PATH="$HOME/jigkit/bin:$PATH"' >> ~/.zshrc
```

Claude Code, `python3`, PyYAML 이 필요하다.

## 사용

```bash
jig list                    # 프로필 목록 (스킬·에이전트·MCP 개수)
jig developer               # 현재 디렉터리를 프로젝트로 세션 시작
jig developer ~/work/proj   # 프로젝트 경로 지정
jig build [프로필]          # build/claude/<name>/ 으로 컴파일
jig doctor [프로필]         # 규칙과 핸드오프 사슬 검사
jig budget [프로필]         # 기동 토큰 실측 + 상한 대조
jig growth 0 10 25 50       # 스킬 N개일 때의 비용 곡선 실측
jig golden [--update]       # 컴파일러 회귀 검사
jig argv developer          # 기동 인자만 출력 (실행하지 않음)
jig new <이름>              # 프로필 생성
```

## 프로필의 정의

도구 중립 파일 두 장. Claude Code 문법은 한 줄도 안 들어간다.

```
profiles/developer/
├── profile.yaml    입출력·권한·스킬·MCP·예산·완료 정의
└── BRIEF.md        순서·경계·자유도
```

스킬·서브에이전트·MCP 정의는 `library/` 에 한 벌만 살고 id 로 참조된다. 그래서 여러
프로필이 복사나 심볼릭 링크 없이 하나를 공유한다. `jig build` 가 그걸 전부 풀어서
`build/claude/<name>/` 을 만든다 — 진짜 Claude Code 플러그인에 설정·MCP 설정·시스템
프롬프트가 붙은 형태다.

프로필은 페르소나가 아니라 **무엇을 읽고, 무엇을 쓰고, 무엇을 못 만지는지**로 정의된다.
[`PRINCIPLES.md`](PRINCIPLES.md#이-설계에-대한-반론--지우지-않고-남긴다) 를 보라 —
이 설계에 대한 가장 강한 공개 반론을 숨기지 않고 남겨뒀다.

## 단계와 핸드오프

작업은 대화가 아니라 **파일**로 넘어간다. 각 단계는 앞 단계의 산출물을 편집할 수 없어서,
이견이 있으면 조용히 고치는 대신 적어야 한다.

| 프로필 | 읽는다 | 쓴다 |
|---|---|---|
| `researcher` | — | `docs/research/{slug}.md` |
| `pm` | research | `docs/prd/{slug}.md` |
| `designer` | prd | `docs/design/{slug}.md` |
| `developer` | design, prd (+review) | `src/**`, `tests/**`, `docs/decisions/{slug}.md` |
| `reviewer` | prd, design (+decisions) | `docs/review/{slug}.md` |

`jig doctor` 가 이 사슬이 끊기면 실패한다 — 아무도 안 만드는 문서를 기다리거나,
아무도 안 읽는 문서를 만들면 잡는다.

### 쓰기 권한은 손으로 적지 않는다

```
deny_write = (모든 프로필의 outputs) − (내 outputs)
```

여섯 번째 프로필을 추가하면 **기존 다섯 개의 파일을 한 줄도 안 고쳐도** 나머지가 그
산출물을 못 쓰게 된다. 손으로 유지하던 때는 이미 구멍이 세 개 나 있었다.

`profile.yaml` 의 `permissions.deny_write` 는 **아무 프로필도 소유하지 않는 경로**에만
쓴다 — 예를 들어 `.github/**`.

이건 denylist 다. 아무도 소유하지 않는 파일(`README.md`, `package.json`)은 누구나 쓸 수
있다. 목적은 단계 경계 유지이지 샌드박스가 아니다.

## 전환

**전환은 프로세스 경계에서만 일어난다.** 스킬과 권한은 프로세스가 시작할 때 묶이고
Claude 는 자기를 재시작할 수 없다. 그래서 세션 안의 `/profile` 은 전환하는 척하지 않는다.
현재 프로필의 완료 조건을 점검하고, `.harness/state.json` 에 상태를 기록하고, 다음에
실행할 명령을 출력한다.

```
> /profile designer
  ✓ developer 완료 조건: 3/4
  ⚠ 테스트 미실행
  다음: 이 세션을 닫고  jig designer
```

## 격리가 뜻하는 것과 뜻하지 않는 것

**뜻한다** — 실측 ([`probe/results/phase0.md`](probe/results/phase0.md)):

- 세션 프로세스에 `core` 와 활성 프로필만 들어간다. 다른 프로필의 스킬은 읽히지도,
  토큰화되지도, 호출되지도 않는다.
- 번들 스킬은 기본으로 꺼진다 (12개 → 1개, 약 1,776 토큰).
- 선언한 MCP 서버만 로드된다. `--strict-mcp-config` 가 다른 모든 MCP 설정을 무시하게 한다.
- 앞 단계 문서는 프롬프트로 부탁하는 게 아니라 권한 계층에서 차단된다.
- `~/.claude/settings.json` 에 아무것도 쓰지 않는다. 두 프로필을 두 터미널에서 동시에
  띄워도 서로를 건드리지 않는다.

**뜻하지 않는다**:

- 파일시스템 격리가 아니다. `Bash` 를 넓게 허용하면 deny 를 우회할 수 있다.
- 세션 중 전환이 아니다. 전부 기동 시점에 결정된다.
- 맥락 연속성이 아니다. 전환하면 대화는 새로 시작한다 — 문서가 핸드오프다.

## 프로필 추가

```bash
jig new qa
# 1) profiles/qa/profile.yaml  — inputs, outputs, done_when
# 2) profiles/qa/BRIEF.md      — 순서·경계·자유도
jig doctor qa
```

코드 변경은 없다. 프로필은 `profiles/*/profile.yaml` 글로빙으로 발견되고,
갱신할 레지스트리 파일이 없다.

추가하기 전에 자문할 것 — 지금 늘어나는 것이 **단계**인가 **직함**인가.
직함이면 만들지 않는다.

## 구조

```
PRINCIPLES.md          원칙, 출처, 그리고 각각을 무엇이 강제하는가
core/                  항상 로드: PREAMBLE.md 와 /profile 스킬
library/               스킬·에이전트·MCP 정의. 한 벌씩만
profiles/<name>/       profile.yaml + BRIEF.md — 도구 중립 원본
adapters/claude/       Claude Code 문법을 아는 유일한 곳
bin/jig                dispatch 만
build/claude/<name>/   컴파일 산출물. --plugin-dir 가 가리키는 곳 (gitignore)
tests/golden/          기대 컴파일 출력
probe/results/         실측 결과와 그것을 만든 명령
```

## 상태

초기다. 프로필 다섯 개가 처음부터 끝까지 동작한다. `library/` 는 **의도적으로 비어 있다** —
반복되는 작업이 드러나서 스킬로 승격할 값이 확인될 때까지 두려는 것이다.
문서는 이 파일 말고는 한국어이고, eval 은 아직 없다.

`[M]` 표시된 주장은 이 기기의 Claude Code 2.1.228 에서 실측했고, 그것을 만든 명령까지
기록돼 있다. 확인 못 한 주장은 `[?]` 와 함께 **어떻게 확인하면 답이 나오는지**를 적어뒀다.
