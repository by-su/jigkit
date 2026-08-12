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
git clone https://github.com/by-su/jigkit
cd jigkit
./bootstrap.sh
```

어디에 클론해도 된다. `bootstrap.sh` 는 자기 위치에서 경로를 유도하므로 하드코딩이 없다.
Claude Code · `python3` · PyYAML · `git` 을 확인하고, 등록된 스킬 소스를
`library/cache/` 로 받고, `jig doctor` 로 실제 동작을 확인한다. 다시 실행해도 안전하다.

PATH 는 **출력만 한다** — 셸 설정을 말없이 고치지 않는다. `--path` 를 주면 추가해 주고,
`--no-sync` 를 주면 네트워크를 타지 않는다.

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

스킬 소스:

```bash
jig source add <url>        # 오픈소스 스킬 저장소 등록
jig source list             # 등록된 소스와 동기화 상태
jig sync [소스]             # 고정된 커밋으로 받는다
jig sync --check            # 업데이트가 있는지만 확인 (아무것도 안 건드림)
jig sync --update [소스]    # 적용하고 무엇이 바뀌었는지 보여준다
jig skills [패턴]           # 쓸 수 있는 스킬과 그 비용
jig usage [프로젝트]        # 무엇이 실제로 불렸는지
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

## 스킬 소스

쓸 만한 스킬은 이미 공개돼 있다. 저장소를 **링크로** 등록한다 — 이 저장소에 커밋되는
것은 링크와 고정된 커밋 SHA 뿐이다.

```bash
jig source add https://github.com/anthropics/skills
jig sync
jig skills
```

`library/sources.yaml` 이 링크와 SHA 를 갖는다. 저장소 내용은 `library/cache/<ns>/` 로
내려오고 gitignore 된다 — 이 프로젝트가 관리하는 것이 아니라 다운로드 결과다.
언제든 지워도 되고 `jig sync` 가 복원한다.

프로필은 id 로 켜거나, 글롭으로 켠다:

```yaml
skills: ["anthropics/*"]                     # 발견 단계 — 통째로
skills: [anthropics/pdf, anthropics/xlsx]    # 측정한 뒤
```

스킬 디렉터리는 컴파일된 플러그인에서 평탄화된다(`anthropics-pdf`). 그래서 두 소스가
같은 이름의 스킬을 가져도 부딪히지 않는다. `SKILL.md` 옆의 `scripts/` · `references/` ·
`templates/` 는 통째로 따라오는데, 기동 시 읽히는 것은 설명뿐이라 세션 비용이 0이다.

### 넓게 시작하고, 측정으로 좁힌다

스킬 마흔 개의 본문을 다 읽고 무엇을 켤지 정하는 것은 현실적이지 않다. 그래서 프로필은
전부 켠 상태로 출발하고, 하네스가 **무엇이 실제로 불리는지**를 기록한다.

`anthropics/skills` 18개로 실측했다 ([`probe/results/growth.md`](probe/results/growth.md)):

| `developer` | 기동 토큰 | 스킬당 |
|---|---:|---:|
| 스킬 0 | 15,625 | — |
| 스킬 18 (`anthropics/*`) | 18,445 | 157 |
| 스킬 32 (`+ obra/*`) | 19,213 | 112 |

`anthropics/skills` 는 스킬당 157 토큰 — 합성 스킬로 잰 70–161 범위의 위쪽 끝이다.
두 번째 소스가 스킬당 싼 것은 설명이 짧기 때문이고, 이는 같은 결론의 반복이다 —
**비용을 정하는 것은 스킬 개수가 아니라 설명 길이다.**

그다음 `jig usage` 가 **프로필별로** 무엇이 불렸고 무엇이 선언만 됐는지 보여준다:

```
developer
  obra/test-driven-development          12회   최근 2026-08-12
  선언했지만 한 번도 안 불림 — 30개

pm
  anthropics/docx                        4회   최근 2026-08-11
  선언했지만 한 번도 안 불림 — 31개
```

기록은 `~/.jigkit/skill-usage.jsonl` 한 곳에 프로젝트를 가로질러 쌓인다. 라이브러리를
프로필별로 어떻게 나눌지는 한 프로젝트만 봐서는 답이 안 나오는 질문이기 때문이다.
레코드마다 `project` 가 남으므로 `jig usage --project <경로>` 로 좁혀 볼 수 있다.

프로필을 좁히는 건 한 줄 편집이다. **자동으로 지우지 않는다.** 50세션에 한 번 불린
스킬이 그 한 번에 결정적일 수 있고, 빈도 카운터는 그걸 알 수 없다.

기록은 컴파일러가 각 프로필 플러그인 안에 심는 `PreToolUse` 훅이 한다. 한 줄 붙이고
**항상 exit 0** 이라 훅이 깨져도 세션을 막지 못한다 — `exit 2` 만 차단하고, `timeout`
으로 죽은 훅도 스킬을 통과시킨다는 것을 실측했다
([`probe/results/skill-usage.md`](probe/results/skill-usage.md)).

### 업데이트

스킬은 데이터가 아니라 **에이전트에게 주는 지시문**이다. 상류가 조용히 바뀌면 에이전트
행동이 리뷰 없이 바뀐다. 그래서 확인과 적용을 분리한다.

```bash
jig sync --check              # 소스당 ls-remote 한 번. 아무것도 안 건드린다
jig sync --update anthropics  # 적용하고, 무엇이 바뀌었는지 보여준다
```

```
anthropics  7029232 -> f17010c

  ~ anthropics/claude-api        설명 변경  73t -> 267t (+194)
  ~ anthropics/frontend-design   설명 변경  99t ->  51t  (-48)
  ~ anthropics/canvas-design     본문만 변경
```

설명 변경을 본문 변경과 따로 세는 이유는, 매 세션이 내는 값이 설명이기 때문이다.
업데이트를 적용하면 `library/sources.yaml` 의 SHA 한 줄이 바뀐다 — 상류 변화가 벤더링된
사본이 아니라 **한 줄 diff** 로 리뷰를 통과한다.

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
bootstrap.sh           첫 설치: 의존성 확인, 캐시 하이드레이션, 동작 검증
core/                  항상 로드: PREAMBLE.md 와 /profile 스킬
library/sources.yaml   등록된 스킬 저장소 — 링크와 고정 SHA
library/cache/<ns>/    받아둔 저장소 내용 (gitignore, 지워도 되는 파생물)
library/               로컬 스킬·에이전트·MCP 정의. 한 벌씩만
profiles/<name>/       profile.yaml + BRIEF.md — 도구 중립 원본
adapters/sources.py    소스 등록·캐시·스킬 해석 (도구 중립)
adapters/claude/       Claude Code 문법을 아는 유일한 곳
bin/jig                dispatch 만
bin/jig-log-skill      스킬 호출을 기록하는 훅
build/claude/<name>/   컴파일 산출물. --plugin-dir 가 가리키는 곳 (gitignore)
tests/golden/          기대 컴파일 출력
probe/results/         실측 결과와 그것을 만든 명령
```

## 상태

초기다. 프로필 다섯 개가 처음부터 끝까지 동작한다. 스킬은 등록한 오픈소스 저장소에서
온다. 프로필은 지금 위에서 설명한 **넓게 켜 둔 발견 단계**에 있고, `jig usage` 데이터가
쌓이기를 기다렸다가 좁힌다. 문서는 이 파일 말고는 한국어이고, eval 은 아직 없다.

`[M]` 표시된 주장은 이 기기의 Claude Code 2.1.228 에서 실측했고, 그것을 만든 명령까지
기록돼 있다. 확인 못 한 주장은 `[?]` 와 함께 **어떻게 확인하면 답이 나오는지**를 적어뒀다.
