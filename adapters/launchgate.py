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


def verdict(state: dict | None, profile: str, env: Mapping[str, str],
            known: set[str] | None = None) -> tuple[str, str]:
    """(`'pass'` | `'bypass'` | `'block'`, 메시지).

    판정의 주인은 `judged`(런처가 기록을 이월할 때 남긴다)이고, 없으면 `profile`
    (그 세션에서 /profile 이 갓 쓴 기록)이다. `known` 은 실존 프로필 집합 —
    런처가 넘긴다. 차단은 넷이 전부 성립할 때뿐이다:
      1. state.json 이 읽혔다
      2. `done` 에 정수 `passed` / `total` 이 있다
      3. `passed < total`
      4. **전진**을 기동한다 — 기록된 `next` 가 방향을 말해 주면 그리로 갈 때만.
         판정 주인의 재기동은 복구 경로("돌아가려면 jig <주인>")라 막으면 되돌아갈
         수 없고, 뒤·옆(이전 단계 재방문)도 전진이 아니므로 막지 않는다.
         `next` 가 없거나 믿을 수 없으면(자기 자신, 실존하지 않는 프로필) 방향을
         모른다 — 다른 프로필 전부를 막는 쪽으로 보수한다 (게이트가 조용히 꺼지는
         것보다 한 번 더 보는 비용이 싸다).
    """
    if not isinstance(state, dict):
        return "pass", ""
    done = state.get("done")
    owner = state.get("judged") if isinstance(state.get("judged"), str) else None
    owner = owner or state.get("profile")
    if not isinstance(done, dict) or not isinstance(owner, str) or not owner:
        return "pass", ""
    passed, total = done.get("passed"), done.get("total")
    if not isinstance(passed, int) or not isinstance(total, int) \
            or isinstance(passed, bool) or isinstance(total, bool):
        # bool 은 int 의 하위 타입이지만 기록으로 인정하지 않는다 — `passed: true` 를
        # 1 로 읽으면 전부 통과한 단계가 "True/4 미완" 으로 차단된다 (판정 반전).
        return "pass", ""
    if passed >= total or owner == profile:
        return "pass", ""
    nxt = state.get("next")
    trusted = (isinstance(nxt, str) and nxt and nxt != owner
               and (known is None or nxt in known))
    if trusted and profile != nxt:
        return "pass", ""  # 전진이 아니다 — 이전 단계 재방문·옆길은 복구 경로다

    if env.get(BYPASS):
        return "bypass", (f"⚠ {BYPASS} — {owner} 미완(done_when {passed}/{total})을 "
                          f"우회하고 기동한다")

    lines = [f"✗ {owner} 단계 미완 (done_when {passed}/{total}"
             + (f" — {state['ts']} 기록)" if state.get("ts") else ")")]
    # unmet 을 쓰는 쪽은 프롬프트 계층이다 — 리스트 대신 문자열이 와도 글자 단위로
    # 쪼개지 말고 한 항목으로 살린다. 그 밖의 이상형은 버린다 (passed/total 과 동일).
    unmet = done.get("unmet")
    if isinstance(unmet, str):
        unmet = [unmet]
    elif not isinstance(unmet, list):
        unmet = []
    lines += [f"  ⚠ {u}" for u in unmet if isinstance(u, str)]
    lines += [f"  돌아가려면:   jig {owner}",
              f"  그래도 진행:  {BYPASS}=1 jig {profile}"]
    return "block", "\n".join(lines)
