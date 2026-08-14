import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Nest 스캐폴드와 `nest g` 가 만드는 spec 은 손대지 않고 그대로 돈다 [M]
    // (probe/results/nest-vitest.md). 그래서 러너는 하나다.
    globals: true,
    // 러너를 **접미사가 아니라 경로로** 가른다. Playwright 의 `seed.spec.ts` 는 루트,
    // 시나리오는 `specs/` 에 있고 Nest 의 spec 은 `src/` 밑에 있다 [M] — 접미사로
    // 가르면 Nest 를 넘겨받지 못하고, 경로로 가르면 둘 다 정확히 갈린다.
    include: [
      "src/**/*.{test,spec}.{ts,tsx}",
      "test/**/*.{test,e2e-spec}.{ts,tsx}",
    ],
    exclude: ["node_modules/**", ".next/**", "dist/**", "specs/**", "*.spec.{ts,tsx}"],
  },
});
