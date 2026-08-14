# 프로필 세션이 CLAUDE.md · AGENTS.md 를 싣는가

Claude Code 2.1.232 환경 · 2026-08-14 · `probe/memory-files/run.sh`

컴파일러는 시스템 프롬프트를 `PREAMBLE + BRIEF (+ 완료 정의 · 입출력)` 로만 조립한다.
사용자 전역 `~/.claude/CLAUDE.md` · 프로젝트 `./CLAUDE.md` · `AGENTS.md` 는 CLI 의
자동 발견 경로라 컴파일러가 손대지 않는다 — **손대지 않는 것과 실리는 것은 다르다.**

샌드박스에 마커를 넣은 `CLAUDE.md`(`PROJECT_MEM_4821`) · `AGENTS.md`(`AGENTS_MEM_9317`)
를 두고, 파일을 읽지 말고 컨텍스트만 보고 답하라고 물었다.

| 실행 | `~/.claude/CLAUDE.md` | `./CLAUDE.md` | `AGENTS.md` |
|---|---|---|---|
| A 맨 `claude` (인자 없음) | 실림 | **실림** | 안 실림 |
| B `--setting-sources user` | 실림 | **안 실림** | 안 실림 |
| C `jig argv developer` 그대로 | 실림 | **안 실림** | 안 실림 |
| D `--setting-sources user,project` | 실림 | 실림 | 안 실림 |
| E `CLAUDE.md` 를 치우고 맨 `claude` | 실림 | — | **안 실림** |

전부 `[M]`. 3열은 이 머신의 전역 `CLAUDE.md` 첫 H1 으로 판정했다 — 샌드박스에 심을 수
없는 유일한 자리라서다. 스크립트가 그 제목을 직접 읽어 쓰므로 다른 머신에서도 성립한다
(`GLOBAL_MARK` 로 덮어쓸 수 있다).

## CLI 가 발견하는 범위는 `CLAUDE.md` 한 장이 아니다

편입이 이보다 좁으면 "적어 뒀는데 안 실린" 상태가 소리 없이 생긴다. 그래서 같이 쟀다 —
`CLAUDE.md` 안에 `@imported.md` 를 두고 `CLAUDE.local.md` 를 옆에 뒀다:

```
1) PROJECT_MEM_4821     ← CLAUDE.md
2) IMPORTED_MEM_2244    ← @ 로 가져온 파일
3) LOCAL_MEM_6688       ← CLAUDE.local.md
```

셋 다 실린다 `[M]`. **`@경로` import 가 펴지고 `CLAUDE.local.md` 도 실린다.**

## `--setting-sources` 는 settings 만이 아니라 프로젝트 메모리도 가른다

A↔B 로 빠지고 B↔D 로 돌아온다 — 다른 인자(`--mcp-config` · `--strict-mcp-config`)는
양쪽에 똑같이 있으므로 귀속은 `--setting-sources` 하나다 `[M]`.

`--help` 는 이 플래그를 "setting sources to load (user, project, local)" 라고만 적는다
`[D]`. **프로젝트 `CLAUDE.md` 자동 발견이 같이 꺼진다는 말은 없다** — 문서로는 알 수
없고 재야 나오는 종류다.

그래서 프로필 세션에서 **프로젝트 `CLAUDE.md` 는 실리지 않는다.** 이 저장소로 치면
`jig developer` 세션은 근거 등급·게이트 회귀 규칙이 적힌 `CLAUDE.md` 를 못 본 채 뜬다.
`--setting-sources user,project` 로 되돌리는 것은 답이 아니다 — 프로젝트
`.claude/settings.json` 의 훅과 권한이 함께 돌아와 이중 발화와 권한 우회를 부른다
(그 배제가 애초에 이 플래그를 붙인 이유다).

### 그래서 바뀐 것

`build.project_memory()` 가 프로젝트 `CLAUDE.md` · `CLAUDE.local.md` 와 그 안의 `@경로`
import 를 읽어 `system-prompt.md` 에 편입한다 (`PREAMBLE` → `BRIEF` → **프로젝트 지침**
→ 완료 정의 → 입출력 — 강제되는 스코프가 뒤에 남는다). `--setting-sources user` 는
그대로 두므로 배선은 여전히 배제된다.

덮지 **않는** 범위가 둘 있다. 프로젝트 **위쪽** 디렉터리의 `CLAUDE.md` 는 안 읽는다 —
`project` 는 사용자가 지정한 경계이므로 그 위는 하네스 밖이다 (모노레포에서
`jig developer packages/api` 로 뜨면 루트 지침이 안 실린다는 뜻이다). 그리고 UTF-8 로
안 읽히는 파일은 **빼고 stderr 로 알린다** — 편입은 부가 기능이고 기동이 본체라,
cp949 로 저장된 `CLAUDE.md` 하나가 `jig run`·`doctor`·`budget` 을 통째로 못 뜨게 하면 안 된다.

### 대가: 프로젝트 텍스트가 시스템 프롬프트로 들어온다

`--setting-sources user` 는 프로젝트가 세션에 손대지 못하게 하려고 붙인 플래그다. 편입은
그중 **내용 채널만** 도로 연다 — 훅·권한은 여전히 배제되지만, 남의 저장소를 클론해
`jig reviewer <그 저장소>` 로 뜨면 그 저장소의 `CLAUDE.md` 가 시스템 프롬프트로 실린다.
권한 deny 는 그대로 서지만 행동 지침은 그렇지 않다. 순서로 일부 완화했을 뿐이므로
(완료 정의·입출력이 뒤에 온다), **신뢰하지 않는 저장소에서 프로필을 띄우지 않는다** 가
현재의 대응이다.

같은 샌드박스에서 다시 쟀다 `[M]`:

```
1) PROJECT_MEM_4821          ← 프로젝트 CLAUDE.md
2) 없음                       ← AGENTS.md (여전히 안 읽힌다)
3) AI Agent Behavioral Guidelines (Karpathy Principles)   ← 사용자 전역
```

golden 은 이 분기를 **지나가지 않는다** — 골든 프로젝트가 `/__golden__` 이라
`CLAUDE.md` 가 없고, 그래서 골든 출력이 머신 독립을 유지한다. 편입이 조용히 빠져도
golden 은 `ok` 를 찍는다는 뜻이라 회귀 검사는 `tests/test_gate.py` 쪽에 넣었다.

## `AGENTS.md` 는 이 버전에서 아예 안 읽힌다

`CLAUDE.md` 가 옆에 있든(A) 없든(E) 안 실린다 `[M]` — **대체(fallback)가 아니라 미지원**이다.
`claude --help` 에도 `AGENTS.md` 를 언급하는 인자가 없다 `[D]`.

이건 스택 쪽에 걸린다: `create-next-app` 의 `--agents-md` 가 기본값이라
(`probe/results/stack-scaffold.md`) 스캐폴드한 프로젝트마다 `AGENTS.md` 가 생기는데
**어느 세션도 그것을 읽지 않는다.** 다른 도구용 파일로 남겨 두든, 만들지 않든,
`CLAUDE.md` 로 합치든 — 셋 중 하나를 고르는 문제이지 "적어 두면 반영된다" 는 아니다.

## 사용자 전역은 전 경로에서 실린다

`~/.claude/CLAUDE.md` 는 A~E 전부에서 실렸다 `[M]`. 즉 프로필의 시스템 프롬프트는
전역 지침 **위에** 얹히는 것이지 그것을 대체하지 않는다. 전역에 "무조건 이렇게 답해라"
류가 있으면 프로필 지침과 충돌한 채 함께 올라간다 — 하네스가 끊어 주지 않는다.

주의: `jig` 는 `os.execvp("claude", …)` 로 띄우므로 셸 함수/별칭으로 감싼 `claude`
(예: `CLAUDE_CONFIG_DIR` 을 바꾸는 래퍼)는 **통과하지 않는다.** 이 머신에서는 래퍼가
빈 값으로 떨어져 기본 `~/.claude` 를 쓰므로 결과가 같았다 `[M]`.
