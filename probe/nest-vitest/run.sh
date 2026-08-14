#!/usr/bin/env bash
# NestJS 에서 Jest 를 빼고 Vitest 하나로 갈 수 있는가?
#
# 카탈로그는 오래 러너를 접미사로 갈랐다 — `*.spec.ts` = Jest, `*.test.ts` = Vitest.
# 근거는 "Jest 가 Nest 스키매틱에 깊이 박혀 있어 지우는 값이 크다" 였다. 러너 둘은
# `pnpm test` 의 뜻을 갈라 놓으므로 줄일 수 있으면 줄이는 게 맞고, 갈림길은 하나다:
#
#   `nest g` 가 **앞으로도 계속** 만들 spec 을 Vitest 가 손 안 대고 돌리는가?
#
#   돌아간다   → 한 번 걷어내면 끝이다
#   안 돌아간다 → 생성될 때마다 사람이 고쳐야 하므로 접미사로 가르는 쪽이 맞다
#
# **카탈로그가 출력한 계획을 그대로 실행한다.** 손으로 흉내 낸 절차가 통과해도
# 실제 배치 경로가 통과한다는 뜻이 아니다 — 재려는 것은 후자다.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SANDBOX="$ROOT/probe/sandbox/nest-vitest"
# 계획의 apply 단계가 `jig` 를 이름으로 부른다 — 설치 여부에 기대지 않는다.
PATH="$ROOT/bin:$PATH"
APP="$SANDBOX/probe-api"

rm -rf "$SANDBOX"; mkdir -p "$SANDBOX"

echo "=== 0) 카탈로그가 낸 계획 ==="
"$ROOT/bin/jig" stack show typescript --with nest --plan "$APP" > "$SANDBOX/plan.txt"
grep -E '^(create|strip|install|apply|normalize|verify)' "$SANDBOX/plan.txt" | sed 's/^/  /'

echo
echo "=== 1) 계획을 순서대로 실행한다 (verify 는 따로 본다) ==="
FAILED=0
while IFS= read -r line; do
  kind="${line%% *}"
  cmd="${line#"$kind"}"; cmd="${cmd#"${cmd%%[![:space:]]*}"}"
  printf '  %-10s' "$kind"
  if ( eval "$cmd" ) > "$SANDBOX/step.log" 2>&1; then
    echo "ok"
  else
    echo "실패 — $cmd"; tail -12 "$SANDBOX/step.log" | sed 's/^/      /'; FAILED=1; break
  fi
done < <(grep -E '^(create|strip|install|apply|normalize)' "$SANDBOX/plan.txt")
[ "$FAILED" -eq 0 ] || exit 1

echo
echo "=== 2) 스캐폴드가 남긴 것 — Jest 자산이 실제로 사라졌는가 ==="
python3 - "$APP/package.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
deps = {**(d.get("dependencies") or {}), **(d.get("devDependencies") or {})}
print("  scripts.test:", d["scripts"]["test"])
print("  package.json 의 jest 키:", "있다" if "jest" in d else "없다")
print("  남은 jest 패키지:", [k for k in deps if "jest" in k] or "없다")
PY
echo "  test/jest-e2e.json: $([ -f "$APP/test/jest-e2e.json" ] && echo 있다 || echo 없다)"
echo "  spec 파일:"
( cd "$APP" && find src test -name '*spec.ts' | sed 's/^/    /' )
echo "  jest.* API 를 쓰는 spec: $( (cd "$APP" && grep -rl '\bjest\.' src test 2>/dev/null) || echo '(없음)' )"

run_verify() {
  while IFS= read -r line; do
    cmd="${line#verify}"; cmd="${cmd#"${cmd%%[![:space:]]*}"}"
    printf '  %-46s' "${cmd#cd * && }"
    if ( eval "$cmd" ) > "$SANDBOX/verify.log" 2>&1; then
      echo "통과"
    else
      echo "실패"; tail -12 "$SANDBOX/verify.log" | sed 's/^/      /'; RC=1
    fi
  done < <(grep -E '^verify' "$SANDBOX/plan.txt")
}

echo
echo "=== 3) 카탈로그의 verify 를 그대로 돌린다 ==="
RC=0
run_verify

echo
echo "=== 4) nest g 가 앞으로 만들 spec 도 도는가 (재발 비용) ==="
# 여기가 갈림길이다. 스캐폴드 spec 한 개는 한 번 고치면 끝이지만 `nest g` 는 계속 만든다.
# resource 는 전송 계층을 대화형으로 물으므로 안 묻는 스키매틱 둘을 쓴다.
( cd "$APP" && npx -y @nestjs/cli generate service widgets \
             && npx -y @nestjs/cli generate controller widgets ) \
  > "$SANDBOX/generate.log" 2>&1 || tail -10 "$SANDBOX/generate.log"
( cd "$APP" && find src -name '*.spec.ts' | sed 's/^/  /' )

echo
# `nest g` 는 Edit 도구를 거치지 않아 포맷 훅이 안 뜬다 — 스캐폴더 출력과 같은 처지라
# 계획의 normalize 를 한 번 더 돌린 뒤에 본다. 안 돌리면 Biome 이 따옴표로 막는다 [M].
( cd "$APP" && pnpm biome check --write . ) > "$SANDBOX/normalize2.log" 2>&1 || true
echo "  --- 생성 후 verify ---"
run_verify

echo
echo "=== 판정 ==="
if [ "$RC" -eq 0 ]; then
  echo "  Jest 없이 카탈로그 계획이 끝까지 간다 ✓ — 러너는 Vitest 하나"
else
  echo "  실패한 verify 가 있다 ✗ — 접미사로 가르는 쪽으로 되돌린다"
fi
exit "$RC"
