# NestJS 에서 Jest 를 빼고 Vitest 하나로 갈 수 있는가

`probe/nest-vitest/run.sh` · @nestjs/core 11 · vitest 4.1.10 · node 24.6.0 · 2026-08-14

카탈로그는 러너를 **접미사로** 갈랐다 — `*.spec.ts` = Jest, `*.test.ts` = Vitest
(`stack-scaffold.md:82-90`). 그때의 근거는 "Jest 가 Nest 의 스키매틱·문서에 깊이 박혀
있어 지우는 값이 크다" 였다. 러너 둘은 `pnpm test` 의 뜻을 갈라 놓으므로 줄일 수 있으면
줄이는 게 맞고, 갈림길은 하나였다:

> `nest g` 가 **앞으로도 계속** 만들 spec 을 Vitest 가 손 안 대고 돌리는가?

돌리면 한 번 걷어내면 끝이고, 못 돌리면 생성될 때마다 사람이 고쳐야 하므로 러너를
줄이는 값이 사라진다.

## 결과 — 카탈로그 계획이 끝까지 간다

**손으로 흉내 낸 절차가 아니라 `jig stack show typescript --with nest --plan` 이 낸 계획을
그대로 실행했다.** create → strip → install → apply → normalize → verify 전부.

```
strip     pnpm remove jest ts-jest @types/jest && pnpm pkg delete jest
                                               && pnpm pkg set scripts.test='vitest run'
strip     rm -f test/jest-e2e.json
```

배치 직후 상태:

| | |
|---|---|
| `scripts.test` | `vitest run` |
| `package.json` 의 `jest` 키 | 없음 |
| 남은 jest 패키지 | 없음 |
| `test/jest-e2e.json` | 없음 |

카탈로그의 verify 넷이 전부 통과한다 — `biome check` · `vitest run` · `tsc --noEmit` ·
`pnpm test`. 한 러너가 파일 5개(스캐폴드 spec · e2e spec · 스모크 테스트 ·
`nest g` 가 만든 spec 둘)를 전부 집는다 `[M]`.

### 재발 비용이 없다 — 이게 판단을 뒤집은 지점

`nest g service` · `nest g controller` 를 돌려 spec 을 새로 만들고 다시 verify 했다.
전부 통과한다. **생성된 spec 중 `jest.*` API 를 쓰는 것이 하나도 없다** `[M]` — 전부
`Test.createTestingModule`(러너 무관)과 `describe/it/expect`(globals) 뿐이라 Vitest 가
그대로 집는다. 예전 판단은 **재발 비용이 있다는 가정** 위에 서 있었고, 그 가정이 틀렸다.

## 접미사가 아니라 경로로 가른다

`*.spec.ts` 를 Vitest 가 집어도 Playwright 와 안 부딪친다 — **Nest 의 spec 은 `src/`
밑, Playwright 의 것은 루트(`seed.spec.ts`)와 `specs/` 에 있다** `[M]`.

```ts
include: ["src/**/*.{test,spec}.{ts,tsx}", "test/**/*.{test,e2e-spec}.{ts,tsx}"],
exclude: ["node_modules/**", ".next/**", "dist/**", "specs/**", "*.spec.{ts,tsx}"],
```

`test/*.e2e-spec.ts` 는 접미사가 달라 따로 적어야 한다. 예전에는 `test/jest-e2e.json` 이
그 자리를 맡았으니 설정 개수는 오히려 하나 줄었다.

## 여기서 잡힌 함정 — 러너를 바꾸면 타입 검사가 먼저 깨진다

`pnpm remove ... @types/jest` 직후 `pnpm tsc --noEmit` 이 깨진다 `[M]`:

```
src/app.controller.spec.ts(5,1): error TS2582: Cannot find name 'describe'.
src/app.controller.spec.ts(8,3): error TS2304: Cannot find name 'beforeEach'.
```

`describe/it/expect` 의 **전역 타입을 주던 것이 `@types/jest`** 였다. 테스트는 초록불인데
게이트만 빨간불이 되는 형태라, 러너만 보고 있으면 놓친다.

tsconfig 의 `compilerOptions.types` 를 고치는 대신 **파일 하나**로 넘긴다:

```ts
// library/stacks/templates/vitest/vitest-globals.d.ts
/// <reference types="vitest/globals" />
```

tsconfig 는 스캐폴더마다 다르고 **이미 존재하므로** 템플릿이 못 건드린다(없는 파일만
만든다). `.d.ts` 는 기본 include 에 걸려서 tsconfig 를 손대지 않고 같은 효과를 낸다.

## 곁다리로 잡힌 것 — `nest g` 출력은 포맷 훅을 안 거친다

`nest g` 직후 `pnpm biome check .` 가 따옴표·import 순서로 막힌다 `[M]`. 포맷 훅은
`PostToolUse` 라 **에이전트가 Edit 으로 고친 파일에만** 뜨고, 스키매틱이 직접 쓴 파일은
지나간다 — 스캐폴더 출력에 `normalize` 가 필요한 것과 같은 이유다. `nest g` 뒤에
`pnpm biome check --write .` 를 한 번 돌리면 verify 넷이 다시 전부 통과한다.

Jest 제거와 무관하게 성립하는 것이라 여기 기록만 해 둔다.
