---
name: example
description: 형식 예시이자 golden 픽스처. 실제 작업에 쓰라고 만든 것이 아니다.
tools: Read, Grep, Glob
---

`library/agents/<id>.md` 의 최소 형태다. 프로필이 `agents: [example]` 로 참조하면
컴파일러가 이 파일을 플러그인의 `agents/` 로 복사한다.

서브에이전트는 별도 컨텍스트 창에서 돌고 요약만 돌려준다. `tools` 로 허용 도구를
좁히는 것이 이 하네스가 쓰는 방식이다 (PRINCIPLES P10).
