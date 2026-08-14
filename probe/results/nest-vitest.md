# NestJS 에서 Jest 를 빼고 Vitest 하나로 갈 수 있는가

`probe/nest-vitest/run.sh` · @nestjs/core 11 · vitest 4.1.10 · node 24.6.0 · 2026-08-14

카탈로그는 지금 러너를 **접미사로** 가른다 — `*.spec.ts` = Jest, `*.test.ts` = Vitest
(`stack-scaffold.md:82-90`). 그때의 판단은 "Jest 가 Nest 의 스키매틱·문서에 깊이 박혀
있어 지우는 값이 크다" 였다. 러너 둘은 `pnpm test` 의 의미를 갈라 놓으므로 줄일 수
있으면 줄이는 게 맞다. 갈림길은 하나였다:

> `nest g` 가 **앞으로도 계속** 만들 spec 을 Vitest 가 손 안 대고 돌리는가?

돌리면 나머지는 기계적인 작업이고, 못 돌리면 생성될 때마다 사람이 고쳐야 하므로
러너를 줄이는 값이 사라진다.

## 결과 — 전부 돈다

스캐폴드가 만든 파일을 **한 글자도 고치지 않고** 돌렸다.

| 대상 | 파일 | Vitest |
|---|---|---|
| 스캐폴드 spec | `src/app.controller.spec.ts` | **1/1 통과** |
| `nest g service widgets` | `src/widgets/widgets.service.spec.ts` | **통과** |
| `nest g controller widgets` | `src/widgets/widgets.controller.spec.ts` | **통과** |
| e2e | `test/app.e2e-spec.ts` | **1/1 통과** (별도 config) |

**생성된 spec 중 `jest.*` API 를 쓰는 것이 하나도 없다** `[M]`. 전부
`Test.createTestingModule`(러너 무관) + `describe/it/expect/beforeEach`(globals) 뿐이라
Vitest 가 그대로 집는다. 재발 비용이 없다 — 이게 판단을 뒤집은 지점이다.

설정은 이것으로 충분했다:

```ts
test: {
  globals: true,
  include: ["src/**/*.{test,spec}.{ts,tsx}", "test/**/*.test.{ts,tsx}"],
  exclude: ["node_modules/**", "dist/**", "specs/**"],
}
```

`*.spec.ts` 를 잡아도 Playwright 와 안 부딪친다 — **Nest 의 spec 은 `src/` 밑,
Playwright 의 것은 루트(`seed.spec.ts`)와 `specs/` 에 있어서 경로로 갈린다** `[M]`.
접미사가 아니라 경로로 가르면 러너 하나로 둘 다 덮인다.

`test/*.e2e-spec.ts` 는 위 include 에 안 걸린다(접미사가 `.e2e-spec.ts`). 별도 config
하나가 더 필요하다 — 지금도 `test/jest-e2e.json` 이 그 자리를 맡고 있으니 개수는 같다.

## 여기서 잡힌 함정 — 러너를 바꾸면 타입 검사가 먼저 깨진다

`pnpm remove jest ts-jest @types/jest` 직후 `pnpm tsc --noEmit` 이 깨진다 `[M]`:

```
src/app.controller.spec.ts(5,1): error TS2582: Cannot find name 'describe'.
src/app.controller.spec.ts(8,3): error TS2304: Cannot find name 'beforeEach'.
```

`describe/it/expect` 의 **전역 타입을 주던 것이 `@types/jest`** 였다. 테스트는 초록불인데
게이트(`typescript` 항목의 `pnpm tsc --noEmit`)만 빨간불이 되는 형태라, 러너만 보고
있으면 놓친다. 고치는 것은 한 줄이다:

```json
"compilerOptions": { "types": ["vitest/globals"] }
```

넣고 나면 `tsc --noEmit` 종료코드 0, `pnpm test`(= `vitest run`) 3/3 통과 `[M]`.

## 걷어낼 것의 목록 (실측으로 확정)

`nest new` 가 깔고 가는 Jest 자산은 넷이고, **둘은 파일이 아니다**:

| 무엇 | 어디 | 지우는 법 |
|---|---|---|
| 패키지 | `jest`, `ts-jest`, `@types/jest` | `pnpm remove` |
| e2e 설정 | `test/jest-e2e.json` | 파일 삭제 |
| **단위 설정** | **`package.json` 안의 `jest` 키** | 파일 삭제로 안 된다 |
| **test 스크립트** | **`package.json` 의 `scripts.test: "jest"`** | 파일 삭제로 안 된다 |

지금 `strippable` 스키마는 `remove:`(명령)와 `files:`(파일 삭제)뿐이라 아래 둘을 못
지운다. **`package.json` 의 키를 다루는 동작이 `stack_apply` 에 새로 필요하다** — 이것이
이 변경의 실제 크기이고, Jest 를 못 빼는 이유는 아니다.

## 결론

접미사로 가르던 판단(`stack-scaffold.md:82-90`)은 **재발 비용이 있다는 가정** 위에 서
있었고, 그 가정이 틀렸다. Jest 를 빼도 `nest g` 는 계속 돌아간다.
