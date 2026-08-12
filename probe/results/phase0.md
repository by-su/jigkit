# Phase 0 실측 결과

- 대상: Claude Code **2.1.228**, macOS (Darwin 25.5.0)
- 일시: 2026-08-12
- 방법: 실제 CLI 실행. 판정은 `loaded / not_loaded / blocked / unsupported / skipped`.

근거 등급은 전부 `[M]` (실측). 확인 못 한 것은 `[?]` 로 남기고 확인 방법을 붙였다.

## 결과

| # | 질문 | 판정 | 근거 |
|---|---|---|---|
| 1 | 플러그인 매니페스트 위치 | **`.claude-plugin/plugin.json`** | 이 위치로 두니 `claude plugin validate <path> --strict` 가 `✔ Validation passed` |
| 2 | `plugin validate` 가 경로를 받는가 | **yes** | 위와 동일. `--strict` 는 author 누락도 실패시킨다 → 매니페스트에 `author` 필수 |
| 3 | `--plugin-dir` 가 스킬을 로드하는가 | **loaded** | alpha 세션이 `alpha:alpha-only` 를 나열. **스킬 이름이 `<plugin>:<skill>` 로 네임스페이스됨** |
| 4 | 다른 프로필 스킬이 안 보이는가 (격리) | **격리됨** | alpha 만 붙인 세션에서 `beta-only` 가 목록에 없음 |
| 5 | `--plugin-dir` 가 부모 디렉터리를 스캔하는가 | **not_loaded** | `--plugin-dir probe/fixtures` (alpha·beta 의 부모) → 스킬 `NONE`. **플래그당 플러그인 루트 하나** |
| 6 | `--append-system-prompt-file` 이 실재하는가 | **loaded** | 파일의 `PROBE_SP_5150` 을 그대로 반복함. `--help` 본문에는 없고 `--bare` 설명에만 언급된다 |
| 7 | `--plugin-dir` 실행이 전역 상태를 건드리는가 | **settings.json 은 건드리지 않음** | `~/.claude/settings.json` 해시·mtime 이 여러 세션 뒤에도 불변. 아래 단서 참고 |
| 8 | `permissions.deny` 가 실제로 편집을 차단하는가 | **blocked** | `--settings` 로 deny 를 주고 `--permission-mode acceptEdits` 로 편집 지시 → 파일 내용 불변, 모델이 BLOCKED 보고 |
| 9 | `skillOverrides` 로 스킬 단위 off 가 되는가 | **not_loaded (미작동)** | 키를 `"alpha:alpha-only"` 와 `"alpha-only"` 두 형식으로 각각 시도 → 두 경우 모두 스킬이 그대로 노출됨 |

## 설계에 직접 반영되는 것

### `[M]` deny 규칙은 `Edit(...)` 로 써야 한다

8번 실행 중 CLI 가 직접 경고를 냈다:

> Permission deny rule … `Write(//…/src/**)` is not matched by file permission checks —
> only `Edit(path)` rules are. Use `Edit(//…/src/**)` instead
> (**Edit rules cover all file-editing tools**).

→ 어댑터는 중립 스키마의 `deny_write` 를 **`Edit(...)` 규칙으로 컴파일**한다.
`Write(...)` 로 쓰면 조용히 통과한다 — 정확히 "조용히 틀리는" 실패 모드다.

경로는 `//` 로 시작하는 절대경로 형식을 썼고 그대로 동작했다.

### `[M]` 격리 방식이 확정됐다 — 단, 주장을 정확히 하자

7번이 이 설계의 근거다. `--plugin-dir` 는 `settings.json` 을 쓰지 않으므로
**두 프로필을 다른 터미널에서 동시에 띄워도 서로를 건드리지 않는다.**
반면 `plugin install/enable` 경로는 `enabledPlugins`·`extraKnownMarketplaces` 를
공유 설정에 쓴다 → 채택하지 않는다.

**단서**: `~/.claude/plugins/known_marketplaces.json` 은 해시가 바뀐다.
확인해 보니 바뀌는 것은 `lastUpdated` 타임스탬프 하나뿐이고, 이는 **어떤 세션이든
기동하면 공식 마켓플레이스를 갱신하면서 생기는 것**이지 `--plugin-dir` 탓이 아니다.
정확한 주장은 이것이다 — **하네스는 사용자 설정에 아무것도 쓰지 않는다.
마켓플레이스 레지스트리의 타임스탬프는 하네스와 무관하게 갱신된다.**

("전역 파일이 전혀 안 바뀐다"고 적었다면 그건 거짓이었을 것이다.
해시 하나가 바뀐 걸 보고 그냥 넘어갔다면 반대로 근거 없는 안심이 됐을 것이다.)

5번 때문에 런처는 **프로필마다 `--plugin-dir` 를 개별로 넘긴다**(core + profile 두 개).

### `[M]` 스킬 단위 on/off 는 쓰지 않는다

9번이 미작동이므로 "필요한 스킬만 로드"는 **플러그인 경계로만** 구현한다.
이 결론은 애초 설계와 같다. 다만 `skillOverrides` 키가 설정 스키마에 존재한다는
보고가 있었으므로, 위 두 키 형식이 틀렸을 가능성은 `[?]` 로 남긴다 —
확인 방법: 세션에서 `/config` 또는 `claude --settings ... -p "/status"` 로
실제 인식된 키를 대조.

## 남은 `[?]`

| 질문 | 확인 방법 |
|---|---|
| `--agent <name>` 이 `--plugin-dir` 로 들어온 에이전트를 이름으로 잡는가 | `claude --plugin-dir <p> --agent <name> -p "역할을 한 줄로"` — 네임스페이스(`<plugin>:<agent>`)도 시도 |
| `Stop` 훅의 `{"decision":"block"}` 이 실제로 턴 종료를 막는가 | 최소 훅 + `-p` 실행 |
| `--resume <id> --plugin-dir <B>` 가 재개 세션에 B의 플러그인을 적용하는가 | 세션 ID 고정 후 2회 실행 대조 (성공 시 맥락 유지 전환이 가능해짐) |
| `claude plugin details` 가 경로를 받는가 (토큰 예산 검사에 필요) | `claude plugin details <build 경로>` |
| `plugin eval --ablation with-without` 이 경로 타겟에서 동작하는가 | `--help` 상 기본값이 경로일 때 `none` 이므로 명시 지정해 확인 |
