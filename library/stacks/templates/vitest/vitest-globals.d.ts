// `describe`/`it`/`expect` 의 전역 타입.
//
// 이 파일이 없으면 러너만 바꿔도 **타입 검사가 먼저 깨진다** — Nest 스캐폴드에서 그
// 전역을 주던 것은 `@types/jest` 였고, 그것을 지우면 테스트는 초록불인데
// `pnpm tsc --noEmit` 게이트만 빨간불이 된다 [M] (probe/results/nest-vitest.md).
//
// tsconfig 의 `compilerOptions.types` 를 고치는 대신 파일 하나로 두는 이유는,
// tsconfig 가 스캐폴더마다 다르고 이미 존재하기 때문이다 — 템플릿은 없는 파일만 만든다.
/// <reference types="vitest/globals" />
