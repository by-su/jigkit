# 빠른 시작

> English: [QUICK_START.md](../QUICK_START.md) · 왜 이렇게 되어 있는지: [README.md](README.md)

빈 기계에서 프로필 세션이 뜰 때까지. 여기 있는 것은 전부 그대로 복사해 실행할 수 있다.

## 1. 준비물

| | 확인 | 없으면 |
|---|---|---|
| Claude Code | `claude --version` | https://claude.com/claude-code |
| Python 3 | `python3 --version` | macOS: `brew install python3` |
| PyYAML | `python3 -c 'import yaml'` | `python3 -m pip install --user PyYAML` |
| git | `git --version` | 스킬 소스를 받으려면 필요하다 |

`bootstrap.sh` 가 넷을 모두 검사하고, 하나라도 없으면 아무것도 하지 않고 멈춘다.

## 2. 설치

```bash
git clone https://github.com/by-su/jigkit
cd jigkit
./bootstrap.sh --path     # 프리플라이트 → 스킬 캐시 → 검증 → PATH 추가
exec "$SHELL" -l          # 새 PATH 를 잡는다
```

- **아무 데나** 클론해도 된다 — `bootstrap.sh` 는 자기 위치에서 경로를 유도한다.
- `--path` 없이 실행하면 `export PATH=...` 한 줄을 *출력만* 한다. 직접 넣으면 된다.
- `--no-sync` 는 네트워크를 타지 않는다. **새 기계에서는 쓰지 않는다** — 스킬 캐시가
  없으면 검증 단계가 실패한다.
- `core/GLOBAL_CLAUDE.md` 를 `~/.claude/CLAUDE.md` 로 쓴다 — 모든 세션이 싣는 기본 전역
  지침이다. **병합이 아니라 덮어쓴다**: 손으로 쓴 전역 지침이 있으면 먼저 옮겨 둔다.
- `--lang English` 를 주면 그때 응답 언어까지 정한다. 나중에는 `jig lang English` 로
  바꾸고, `jig lang` 만 치면 지금 값을 보여준다.
- 여러 번 실행해도 안전하고, 같은 상태가 된다.

됐는지 확인:

```bash
jig list       # 프로필 다섯 개, 스킬·에이전트·MCP 개수와 함께
jig doctor     # 규칙과 핸드오프 사슬
```

### 이미 Claude Code 가 깔린 기계에서 시작할 때

`reset-and-setup.sh` 는 Claude Code 를 방금 설치한 상태로 되돌린 다음 부트스트랩한다.
그 파일 하나만 옮기면 된다 — 옆에 jigkit 클론이 없으면 스스로 클론한다.

```bash
./reset-and-setup.sh --dry-run   # 무엇이 지워지는지만, 그 외에는 아무것도 안 한다
./reset-and-setup.sh --path      # 백업 → 리셋 → 클론 → 부트스트랩
```

- 지우기 전에 `~/.claude-reset-backups/` 로 `tar` 백업이 먼저 떨어진다.
  `--restore <파일>` 로 되돌린다.
- `--keep-history` 는 대화와 메모리(`~/.claude/projects/`)를 남긴다.
- **Claude 를 먼저 닫는다.** 열려 있으면 실행을 거부한다 — 데스크톱 앱과 CLI 가
  `~/.claude` 를 공유하고 종료할 때 다시 쓰기 때문에, 살아 있는 세션 밑에서 한 리셋은
  조용히 되돌려진다.

## 3. 네 줄 요약

- **프로필**은 페르소나가 아니라 작업 단계다: `researcher → pm → designer → developer → reviewer`.
- 스킬·MCP·권한은 **프로세스가 뜨는 시점에** 정해진다.
- 단계 사이는 대화가 아니라 **파일**로 넘어간다 — 뒷 단계는 앞 단계의 산출물을 고칠 수 없다.
- 그래서 단계 전환은 새 세션을 여는 일이다. 세션 도중 전환은 없다.

## 4. 세션 열기

```bash
jig list                   # 어떤 프로필이 있는지
jig developer              # 현재 디렉터리를 프로젝트로
jig developer ~/work/app   # 또는 지정해서
jig argv developer         # 실행하지 않고 기동 인자만 출력
```

## 5. 스킬 추가

스킬은 오픈소스 저장소에서 온다. 커밋되는 것은 링크와 고정된 커밋뿐이다.

```bash
jig source add https://github.com/anthropics/skills
jig sync                   # 등록된 ref 대로 캐시를 맞춘다
jig skills                 # 쓸 수 있는 것과, 각각이 기동 때 무는 비용
```

`profiles/<이름>/profile.yaml` 에서 glob 이나 id 로 켠다:

```yaml
skills: ["anthropics/*"]                     # 탐색 — 전부 켠다
skills: [anthropics/pdf, anthropics/xlsx]    # 재고 나서
```

그다음은 사용 기록이 정한다:

```bash
jig usage                          # 무엇이 실제로 불렸는지, 전 프로젝트 합산
jig usage --project ~/work/app     # 한 곳만
```

업스트림 업데이트는 일부러 두 단계다 — 스킬은 에이전트에게 주는 지시라, 조용한
업스트림 변경은 조용한 행동 변경이다:

```bash
jig sync --check                # 업데이트가 있나? 아무것도 건드리지 않는다
jig sync --update anthropics    # 적용하고, 무엇이 바뀌었는지 보여준다
```

## 6. 프로젝트 세팅 (스택)

스택은 *프로젝트*가 무엇으로 돌아가는지를 배치한다 — 포맷터 훅, 게이트, MCP 정의.

```bash
jig stack list                       # 카탈로그, 그리고 어떤 말이 어디로 가는지
jig stack show web-app               # 그 조합이 무엇을 배치하는지
jig stack show web-app --plan ./app  # 실행할 명령 목록, 순서대로
jig stack apply web-app ./app        # dry-run
jig stack apply web-app ./app --apply
jig stack check web-app ./app        # 선언 ↔ 실제 대조
```

- `apply` 는 **`--apply` 가 없으면 dry-run** 이다.
- `apply` 는 **배선만 하고 설치하지 않는다.** 프로젝트 생성과 도구 설치는 `--plan` 목록의
  몫이고, `apply` 는 드리프트가 나면 안 되는 것만 쓴다.
- 프리셋이 alias 를 쥐고 있어서 `jig stack show fastapi` 와 `jig stack show api` 는 같다.

## 7. 다음 단계로

세션 안에서:

```
> /profile designer
  ✓ developer 단계 완료 조건: 3/4
  ⚠ 테스트 미실행
  다음: 이 세션을 닫고  jig designer
```

완료 조건을 점검하고, 판정을 `.harness/state.json` 에 기록하고, 실행할 명령을 알려준다.
그다음 세션을 닫고 그 명령을 실행한다.

앞 단계가 덜 끝났으면 **전진** 기동은 거부된다:

```bash
jig developer                        # 같은 프로필 재기동이 복구 경로다
JIG_GATE_BYPASS=1 jig reviewer       # 그래도 진행 — 플래그가 아니라 환경 변수라 흔적이 남는다
```

## 8. 걸려 넘어지는 것들

- **격리는 샌드박스가 아니다.** 넓은 `Bash` 권한은 deny 규칙을 우회할 수 있고, 쓰기 권한은
  *denylist* 다 — 어떤 프로필도 소유하지 않는 파일(`README.md`, `package.json`)은 모두에게
  열려 있다.
- **전환은 새 대화다.** 핸드오프는 문서이고, 맥락은 넘어가지 않는다.
- **스킬 설명을 짧게 쓴다.** 쓰든 안 쓰든 모든 세션이 모든 설명값을 낸다(짧으면 ~70토큰,
  길면 ~161토큰). 본문은 호출 전까지 공짜다.
- **자동으로 쳐내는 것은 없다.** `jig usage` 는 보고만 하고, 프로필을 좁히는 한 줄은 사람이
  고친다.
- **새 기계에서 `--no-sync`** 를 주면 스킬 캐시가 없어 `jig doctor` 가 실패한다.

## 9. 뭔가 잘못됐을 때

| 증상 | 조치 |
|---|---|
| `jig: command not found` | PATH 줄이 없다 — `./bootstrap.sh --path`, 아니면 그냥 `./bin/jig` |
| 부트스트랩이 `FAIL PyYAML` 에서 멈춘다 | `python3 -m pip install --user PyYAML` |
| `reset-and-setup.sh` 가 실행을 거부한다 | Claude 데스크톱 앱과 모든 `claude` 세션을 닫는다 |
| 프로필을 고친 뒤 `jig doctor` 실패 | 아무도 만들지 않는 문서를 기다리거나, 아무도 읽지 않는 문서를 만드는 프로필이 있다 |
| 새로 클론했는데 스킬이 없다 | `jig sync` |

## 다음

- [`README.md`](README.md) — 왜 프로필을 나누는지, 무엇을 쟀는지, 격리가 뜻하는 것과
  뜻하지 않는 것.
- [`PRINCIPLES.md`](../PRINCIPLES.md) — 원칙과 출처, 그리고 이 설계에 대한 가장 강한 반론.
