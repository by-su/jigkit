import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // `*.spec.ts` 는 vitest 가 잡지 않는다. 설정이 없으면 두 곳에서 충돌한다 [M]:
    //   - Playwright 가 만드는 루트 `seed.spec.ts` → `test.describe()` 실행 실패
    //   - NestJS 스캐폴드의 `src/**/*.spec.ts` → Jest 용인데 vitest 가 같이 집는다
    // 그래서 러너를 접미사로 가른다: `*.test.ts` = vitest, `*.spec.ts` = 그 도구의 러너.
    include: ["src/**/*.test.{ts,tsx}", "test/**/*.test.{ts,tsx}"],
    exclude: ["node_modules/**", ".next/**", "dist/**", "specs/**"],
  },
});
