#!/usr/bin/env bash
# Vitest 가 `nest new` 가 만든 `*.spec.ts` 를 **손 안 대고** 돌리는가?
#
# 지금 카탈로그는 러너를 접미사로 가른다 — `*.spec.ts` = Jest, `*.test.ts` = Vitest.
# 러너 하나로 줄일 수 있으면 줄이는 게 맞지만, 갈림길은 이 한 가지다:
#
#   돌아간다   → strip + 설정 교체만 하면 된다 (우리가 아는 기계적 작업)
#   안 돌아간다 → `nest g` 가 앞으로도 Jest 스타일 spec 을 뱉으므로 매번 사람이 고쳐야 한다
#                 → 접미사로 가르는 지금이 맞다
#
# 스캐폴드가 만든 파일을 **한 글자도 고치지 않고** 돌리는 것이 이 프로브의 전부다.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SANDBOX="$ROOT/probe/sandbox/nest-vitest"

rm -rf "$SANDBOX"; mkdir -p "$SANDBOX"

echo "=== 0) nest new (카탈로그의 create 명령 그대로) ==="
( cd "$SANDBOX" && npx -y @nestjs/cli new probe-api -p pnpm --skip-git --strict ) \
  > "$SANDBOX/scaffold.log" 2>&1 || { tail -20 "$SANDBOX/scaffold.log"; exit 1; }
APP="$SANDBOX/probe-api"

echo "  생성된 spec 파일:"
( cd "$APP" && find src test -name '*.spec.ts' | sed 's/^/    /' )
echo "  scripts.test: $(python3 -c "import json;print(json.load(open('$APP/package.json'))['scripts']['test'])")"

echo
echo "=== 1) 스캐폴드 그대로 Jest 로 돌린다 (기준선) ==="
( cd "$APP" && pnpm test ) > "$SANDBOX/jest.log" 2>&1 && JEST_RC=0 || JEST_RC=$?
grep -E "Tests:|Suites:|✓|✗" "$SANDBOX/jest.log" | tail -5 | sed 's/^/  /' || true
echo "  종료코드 $JEST_RC"

echo
echo "=== 2) Vitest 를 넣는다. spec 파일은 건드리지 않는다 ==="
( cd "$APP" && pnpm add -D vitest ) > "$SANDBOX/install.log" 2>&1

# 카탈로그 템플릿에서 바꿀 후보. Nest 의 spec 은 src/ 밑, Playwright 의 것은 루트·specs/ 에
# 있으므로 경로로 가르면 두 러너의 파일이 섞이지 않는다.
cat > "$APP/vitest.config.ts" <<'TS'
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    include: ["src/**/*.{test,spec}.{ts,tsx}", "test/**/*.test.{ts,tsx}"],
    exclude: ["node_modules/**", "dist/**", "specs/**"],
  },
});
TS

echo "  vitest.config.ts include: src/**/*.{test,spec}.ts"
echo
echo "=== 3) Vitest 로 같은 spec 을 돌린다 ==="
( cd "$APP" && pnpm vitest run ) > "$SANDBOX/vitest.log" 2>&1 && VITEST_RC=0 || VITEST_RC=$?
sed 's/^/  /' "$SANDBOX/vitest.log" | tail -25
echo "  종료코드 $VITEST_RC"

echo
echo "=== 4) nest g 가 앞으로 만들 spec 도 도는가 (재발 비용) ==="
# 여기가 실제 갈림길이다. 스캐폴드 spec 한 개는 한 번 고치면 끝이지만,
# `nest g` 는 앞으로도 계속 spec 을 만든다. 그것이 jest.* API 를 쓰면
# **생성될 때마다** 사람이 고쳐야 하므로 러너를 줄이는 값이 사라진다.
# resource 는 전송 계층·CRUD 를 대화형으로 묻는다. 프로브는 멈추면 안 되므로
# 안 묻는 스키매틱 둘로 같은 것을 본다 — 둘 다 spec 을 만든다.
( cd "$APP" && npx -y @nestjs/cli generate service widgets \
             && npx -y @nestjs/cli generate controller widgets ) \
  > "$SANDBOX/generate.log" 2>&1 || { tail -20 "$SANDBOX/generate.log"; }
echo "  생성된 spec:"
( cd "$APP" && find src -name '*.spec.ts' | sed 's/^/    /' )
echo "  jest.* API 를 쓰는 spec:"
( cd "$APP" && grep -rln '\bjest\.' src test 2>/dev/null | sed 's/^/    /' || echo "    (없음)" )

( cd "$APP" && pnpm vitest run ) > "$SANDBOX/vitest-gen.log" 2>&1 && GEN_RC=0 || GEN_RC=$?
grep -E "Test Files|Tests " "$SANDBOX/vitest-gen.log" | sed 's/^/  /' || true
echo "  종료코드 $GEN_RC"

echo
echo "=== 5) e2e spec (test/*.e2e-spec.ts) ==="
# 스캐폴드가 test/jest-e2e.json 을 별도로 깐다. 접미사가 `.e2e-spec.ts` 라
# 위 include 에 안 걸린다 — Vitest 로 옮기려면 이것도 잡아야 한다.
cat > "$APP/vitest.e2e.config.ts" <<'TS'
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    include: ["test/**/*.e2e-spec.{ts,tsx}"],
  },
});
TS
( cd "$APP" && pnpm vitest run --config vitest.e2e.config.ts ) \
  > "$SANDBOX/vitest-e2e.log" 2>&1 && E2E_RC=0 || E2E_RC=$?
grep -E "Test Files|Tests |Error|FAIL" "$SANDBOX/vitest-e2e.log" | head -8 | sed 's/^/  /' || true
echo "  종료코드 $E2E_RC"

echo
echo "=== 6) Jest 를 실제로 걷어내면 타입 검사가 남는가 ==="
# `describe/it/expect` 의 전역 타입은 @types/jest 가 준다. 그것을 지우면
# `pnpm tsc --noEmit` (카탈로그의 게이트) 가 깨진다 — 러너를 바꾸는 일은
# 테스트 실행뿐 아니라 **타입 검사**까지 옮기는 일이다.
( cd "$APP" && pnpm remove jest ts-jest @types/jest ) > "$SANDBOX/remove.log" 2>&1
python3 - "$APP/package.json" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
d.pop("jest", None)                       # 설정이 별도 파일이 아니라 이 안에 있다
d["scripts"]["test"] = "vitest run"
json.dump(d, open(p, "w"), indent=2, ensure_ascii=False)
PY
rm -f "$APP/test/jest-e2e.json"

echo "  --- @types/jest 없이 tsc (tsconfig 손대기 전) ---"
( cd "$APP" && pnpm tsc --noEmit ) > "$SANDBOX/tsc-before.log" 2>&1 && TSC1=0 || TSC1=$?
head -4 "$SANDBOX/tsc-before.log" | sed 's/^/    /'
echo "    종료코드 $TSC1"

python3 - "$APP/tsconfig.json" <<'PY'
import json, re, sys
p = sys.argv[1]
raw = open(p).read()
raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)          # nest 는 주석이 든 tsconfig 를 깐다
raw = re.sub(r",(\s*[}\]])", r"\1", raw)
d = json.loads(raw)
d["compilerOptions"]["types"] = ["vitest/globals"]
json.dump(d, open(p, "w"), indent=2)
PY

echo "  --- tsconfig 에 types: [\"vitest/globals\"] 를 넣고 다시 ---"
( cd "$APP" && pnpm tsc --noEmit ) > "$SANDBOX/tsc-after.log" 2>&1 && TSC2=0 || TSC2=$?
head -4 "$SANDBOX/tsc-after.log" | sed 's/^/    /'
echo "    종료코드 $TSC2"

echo "  --- Jest 없이 pnpm test (= vitest run) ---"
( cd "$APP" && pnpm test ) > "$SANDBOX/final.log" 2>&1 && FINAL=0 || FINAL=$?
grep -E "Test Files|Tests " "$SANDBOX/final.log" | sed 's/^/    /' || true
echo "    종료코드 $FINAL"

echo
echo "=== 판정 ==="
echo "  스캐폴드 spec       $([ "$VITEST_RC" -eq 0 ] && echo '통과' || echo '실패')"
echo "  nest g 가 만든 spec  $([ "$GEN_RC" -eq 0 ] && echo '통과' || echo '실패')"
echo "  e2e spec            $([ "$E2E_RC" -eq 0 ] && echo '통과' || echo '실패')"
echo "  Jest 제거 후 tsc     $([ "$TSC1" -eq 0 ] && echo '통과' || echo '실패') → types 지정 후 $([ "$TSC2" -eq 0 ] && echo '통과' || echo '실패')"
echo "  Jest 제거 후 pnpm test $([ "$FINAL" -eq 0 ] && echo '통과' || echo '실패')"
echo
if [ "$VITEST_RC" -eq 0 ] && [ "$GEN_RC" -eq 0 ]; then
  echo "  Vitest 가 Nest 의 spec 을 손 안 대고 돌린다 ✓ — Jest 를 뺄 수 있다"
else
  echo "  Vitest 가 Nest 의 spec 을 못 돌린다 ✗ — 접미사로 가르는 지금이 맞다"
  echo "  (실패 원인은 $SANDBOX/vitest*.log)"
fi
