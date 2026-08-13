# 스캐폴더가 린터를 어떻게 고르는가

Claude Code 2.1.228 환경 · 2026-08-13

`create` 문자열은 스택 데이터에 그대로 들어가고 스킬이 그것을 돌린다. 인자를 추측하면
"우리가 정한 도구로 세팅된다" 는 전제가 첫 단계에서 깨진다. 그래서 쟀다.

## create-next-app

```bash
npx --yes create-next-app@latest --help
```

관련 인자 `[M]`:

| 인자 | 뜻 |
|---|---|
| `--eslint` | ESLint 설정으로 초기화 |
| **`--biome`** | **Biome 설정으로 초기화** |
| `--yes` | 지정하지 않은 옵션은 저장된 선호·기본값을 쓴다 (없으면 **대화형으로 멈춘다**) |
| `--agents-md` | `AGENTS.md` 를 포함 (기본값) |
| `--ts` / `--app` / `--use-pnpm` | 기본 조합 |

`--no-eslint` 는 없다. 대신 `--biome` 가 린터 선택 자체를 바꾼다.

**그래서 바뀐 것**: `typescript.yaml` 의 `next.create` 는
`... --ts --app --biome --use-pnpm --yes` 이고, `strips: [eslint]` 는 **지웠다** — 애초에
설치되지 않으므로 지울 것이 없다. `--yes` 가 빠지면 대화형 프롬프트에서 멈추므로 필수다.

`strips` 기계장치 자체는 남는다 — 아래 `nest` 가 그 경우다.

## @nestjs/cli new

```bash
npx --yes @nestjs/cli new --help
npx --yes @nestjs/cli new api --directory <경로> --package-manager pnpm --skip-git --strict --dry-run
```

인자 `[M]`: `--directory` · `-d/--dry-run` · `-g/--skip-git` · `-s/--skip-install` ·
`-p/--package-manager` · `-l/--language` · `-c/--collection` · `--strict`.
**린터 선택 인자가 없다** — `.prettierrc` 와 `eslint.config.mjs` 가 항상 만들어진다.
`strips: [eslint, prettier]` 가 여기서 정당화된다.

### 이 스캐폴더는 경로를 다룰 줄 모른다 — 세 가지가 각각 틀린다

| 준 것 | 실제로 만든 곳 |
|---|---|
| `nest new <절대경로>` | 경로를 **소문자로 낮춘다** (`-Users-arto-Desktop` → `-users-arto-desktop`) |
| `nest new x --directory <절대경로>` | 앞의 `/` 를 떼고 **상대경로로 취급** — 현재 디렉터리 밑에 만든다 |
| `nest new MyApi` | **`my-api/`** — 이름을 kebab-case 로 바꾼다 |

전부 `[M]`. 두 번째는 실제로 이 저장소 안에 `private/tmp/…/nest-probe/` 를 만들었다(치웠다) —
**조용히 다른 곳에 만들어지는 것이 가장 나쁜 형태다.**

그래서 `create` 는 **부모에서 이름만 주고** 돌린다:

```
cd {parent} && npx -y @nestjs/cli new {name} -p pnpm --skip-git --strict
```

`{parent}` · `{name}` 플레이스홀더를 `plan()` 에 추가했다. 대상 디렉터리 이름은 kebab-case
여야 하고, 아니면 바로 다음 `cd {dir}` 단계가 실패한다 — 세 번째 함정에 대한 **소리 나는**
방어다. `-p pnpm` 이 없으면 패키지 매니저 프롬프트에서 멈춘다 `[M]`.

### strips 목록은 스캐폴더별로 나눠야 한다

`pnpm remove` 는 없는 의존성에 **에러를 낸다** (`ERR_PNPM_CANNOT_REMOVE_MISSING_DEPS`) `[M]`.
그래서 "eslint 를 지운다" 를 언어 하나의 목록으로 둘 수 없다 — Next 와 Nest 의 패키지 집합이
다르므로 Next 용 이름을 Nest 프로젝트에 지우라고 하면 그 자리에서 깨진다.

`nest new` 의 devDependencies 실측 `[M]`:

```
@eslint/eslintrc @eslint/js @nestjs/cli @nestjs/schematics @nestjs/testing
@types/express @types/jest @types/node @types/supertest eslint eslint-config-prettier
eslint-plugin-prettier globals jest prettier source-map-support supertest ts-jest
ts-loader ts-node tsconfig-paths typescript typescript-eslint
```

`strippable` 을 `nest-eslint` · `nest-prettier` 로 나누고 위 이름을 그대로 넣었다.

### Jest 는 남긴다 — 접미사로 가른다

스캐폴드가 `src/**/*.spec.ts` · `test/jest-e2e.json` · Jest 의존성과 **`package.json` 안의
jest 설정 블록**(별도 파일이 아니다)을 함께 깐다. `scripts.test` 는 `jest` 다 `[M]`.

Jest 는 Nest 의 스키매틱·문서에 깊이 박혀 있어 지우는 값이 크다(설정이 `package.json` 안에
있어 `rm -f` 로도 안 된다). 그래서 러너를 **접미사로** 가른다: `*.spec.ts` = Jest,
`*.test.ts` = Vitest. `vitest.config.ts` 의 `include` 를 `src/**`·`test/**` 의 `*.test.*` 로
좁혀 두 러너가 같은 파일을 주장하지 않게 했고, `nest.verify` 에 `pnpm test`(Jest)를 넣어
스캐폴드의 테스트도 검증에 들어온다.

## shadcn init — 프롬프트에서 멈춘다

`web-app` 프리셋을 실제로 끝까지 돌려 보고 잡았다. `npx shadcn@latest init` 은
**"Select a component library" 프롬프트에서 멈춘다** `[M]` — 스크립트로 돌리면 거기서 죽고
`components.json` 이 안 생긴다. 그래서 `jig stack check` 가 `shadcn 감지 실패` 를 냈다.

```bash
npx --yes shadcn@latest init --help
```

| 인자 | 뜻 |
|---|---|
| `-b, --base <base>` | 컴포넌트 라이브러리 (`base` · `radix` · `aria`) — **이게 그 프롬프트다** |
| `-d, --defaults` | `--template=next --preset=base-nova` |
| `-y, --yes` | 확인 프롬프트 생략 (기본값 true) |

`init: npx shadcn@latest init --base base --defaults` 로 고쳤고, 다시 돌려 `check` 가 통과했다.

## 두 도구가 같은 파일을 주장한다 — vitest ↔ Playwright

`npx playwright init-agents --loop=claude` 는 `seed.spec.ts` · `specs/` ·
`.claude/agents/playwright-test-{planner,generator,healer}.md` · **`.mcp.json`** 을 만든다 `[M]`.
(agents 표면이 실제로 동작하는 것을 여기서 확인했다.)

그 결과 두 가지가 깨졌다:

1. `pnpm vitest run` 이 `seed.spec.ts` 를 수집해 `test.describe()` 를 실행하려다 실패
   → `templates/vitest/vitest.config.ts` 에서 `include: ["**/*.test.{ts,tsx}"]` 로 좁혔다.
2. `pnpm biome check .` 가 남이 만든 파일의 따옴표·import 순서로 실패
   → 언어 파일에 `normalize` 를 넣고 `--plan` 이 init 뒤 apply 앞에 한 번 돌린다.

`.mcp.json` 은 프로필 세션에서는 무시된다(`--strict-mcp-config`) — 그래서 스택의 MCP 는
`library/mcp/<id>.json` 으로 따로 나간다. 설계가 이유 있게 그렇게 돼 있음을 확인한 셈이다.

## normalize 는 apply **뒤**에 와야 한다

처음에는 `normalize`(포맷 정리)를 apply 앞에 뒀다 — "훅이 붙기 전에 기준선을 맞춘다" 는
생각이었는데 **틀렸다** `[M]`. 설정 파일(`biome.json`)을 배치하는 것이 apply 이므로, 앞에서
정리하면 도구 **기본값**(Biome 은 탭 인덴트)으로 포맷한 뒤 규칙이 스페이스로 바뀌어
`pnpm biome check .` 이 13개 파일에서 전부 실패했다.

순서를 `apply` → `normalize` → `verify` 로 바꿨다.

## Biome 이 NestJS 의 의존성 주입을 깨뜨린다

`nest-api` 를 끝까지 돌려서 잡았다. `pnpm test`(Jest)가 이렇게 실패했다 `[M]`:

```
Nest can't resolve dependencies of the AppController (?).
- This commonly occurs when using 'import type' instead of 'import' for injectable classes
```

`biome check --write` 의 `style/useImportType` 이 `import { AppService }` 를
`import type { AppService }` 로 바꿨고, 데코레이터 메타데이터로 주입하는 Nest 는 타입 전용
import 로 **지워진** 심볼을 런타임에 찾지 못한다. `tsc --noEmit` 은 통과한다 — **타입 검사로는
안 잡히고 테스트에서만 터지는** 종류다.

`templates/biome/biome.json` 에서 `style.useImportType: "off"` 로 껐다. 같은 파일에서
`rules.recommended: true` 가 Biome 2.5 에서 **deprecated** 임도 확인해(`preset` 을 쓰라고 한다)
`rules.preset: "recommended"` 로 고쳤다 `[M]` (biome 2.5.8).

## 두 언어 끝단 확인

세 프리셋을 각각 실제로 만들어 `--plan` 의 모든 단계를 돌렸다.

| | `api` (python) | `web-app` (typescript) | `nest-api` (typescript) |
|---|---|---|---|
| `--plan` 전 단계 | 통과 | 통과 | 통과 |
| verify | `ruff check` 0 · `pytest -q` 1 passed | `biome check` 0 · `vitest run` 1 passed · `tsc` 0 · `prisma validate` 0 | `biome check` 0 · `vitest run` 0 · `tsc` 0 · **`pnpm test`(Jest) 1 passed** · `prisma validate` 0 |
| `jig stack check` | 빈 목록 | 빈 목록 | 빈 목록 |

스모크 테스트 템플릿이 없으면 `pytest -q` 가 `no tests ran` 으로 나가 verify 가 신호를
못 준다 — 넣은 이유가 실측으로 확인됐다. `nest-api` 는 Vitest(우리 `*.test.ts`)와
Jest(스캐폴드의 `*.spec.ts`)가 **둘 다 초록불**이다.
