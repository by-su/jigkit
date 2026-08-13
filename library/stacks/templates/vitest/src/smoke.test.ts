// 스모크 테스트. 이 한 개가 있어야 갓 만든 프로젝트에서도 `vitest run` 이 신호를 준다.
// 테스트가 0개면 vitest 는 "No test files found" 로 실패하고, verify 의 통과·실패가
// 프로젝트 상태와 무관해진다. 실제 테스트가 생기면 지운다.
import { expect, test } from "vitest";

test("smoke", () => {
  expect(true).toBe(true);
});
