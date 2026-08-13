"""기동 게이트 — 이전 단계가 done_when 미충족으로 끝났다는 기록이 있으면 전진을 막는다.

`/profile` 스킬이 완료 조건을 판정해 `.harness/state.json` 의 `done` 에 남기고,
`jig <profile>` 이 기동 직전에 그 기록을 읽는다. 스킬은 판단(자연어 조건 포함),
런처는 결정론 — P07 의 분업이다. 미완인 채 다음 단계로 넘어가지 않도록 기억하는
주체가 이 게이트 전에는 사용자였다.

**커밋 게이트와 반대 방향의 fail-open 이다.** 커밋 게이트는 판단 불가 시 켜진 채로
남는다(놓치면 장치가 없는 것과 같으므로). 여기는 기록 부재가 정상 경로에 흔하다 —
스킬이 안 불린 세션, 탐색용 기동, 구 스키마. 그래서 **기록된 미충족에만 반응**하고
나머지는 조용히 통과시킨다. 이건 강제가 아니라 기억 대행이고, `done` 을 쓰는 쪽이
프롬프트 계층인 이상 그 이상일 수도 없다.

stdlib 전용 — `tests/test_gate.py` 가 PyYAML 없이 돌아야 하므로 cli/build 를
import 하지 않는다. 판정만 하고, 출력과 종료는 호출자 몫이다.
"""
from __future__ import annotations

from typing import Mapping

# 값이 아니라 **비어 있지 않음**으로 판정한다. 커밋 게이트의 우회가 `BYPASS=` 대입의
# 존재로 정해지는 것과 같은 결 — 환경변수인 이유도 같다: 트랜스크립트에 흔적이 남는다.
BYPASS = "JIG_GATE_BYPASS"


def verdict(state: dict | None, profile: str, env: Mapping[str, str]) -> tuple[str, str]:
    """(`'pass'` | `'bypass'` | `'block'`, 메시지).

    차단은 넷이 전부 성립할 때뿐이다:
      1. state.json 이 읽혔다
      2. `done` 에 정수 `passed` / `total` 이 있다
      3. `passed < total`
      4. 기록된 프로필과 **다른** 프로필을 기동한다 — 같은 프로필 재기동은
         곧 복구 경로("돌아가려면 jig <prev>")라 막으면 되돌아갈 수 없다.
    """
    if not isinstance(state, dict):
        return "pass", ""
    done, prev = state.get("done"), state.get("profile")
    if not isinstance(done, dict) or not isinstance(prev, str) or not prev:
        return "pass", ""
    passed, total = done.get("passed"), done.get("total")
    if not isinstance(passed, int) or not isinstance(total, int):
        return "pass", ""  # 이상형 스키마 — 기록으로 인정하지 않는다 (fail-open)
    if passed >= total or prev == profile:
        return "pass", ""

    if env.get(BYPASS):
        return "bypass", (f"⚠ {BYPASS} — {prev} 미완(done_when {passed}/{total})을 "
                          f"우회하고 기동한다")

    lines = [f"✗ {prev} 단계 미완 (done_when {passed}/{total}"
             + (f" — {state['ts']} 기록)" if state.get("ts") else ")")]
    lines += [f"  ⚠ {u}" for u in (done.get("unmet") or []) if isinstance(u, str)]
    lines += [f"  돌아가려면:   jig {prev}",
              f"  그래도 진행:  {BYPASS}=1 jig {profile}"]
    return "block", "\n".join(lines)
