# SessionStart 훅 — stdout 이 컨텍스트에 주입되는가

날짜: 2026-08-13 · Claude Code 2.1.228 · 재현: `probe/session-start/run.sh`

## 결론

**주입된다 `[M]`.** matcher `startup` 인 SessionStart 훅의 stdout 이 `-p`(헤드리스)
세션에서도 에이전트 컨텍스트에 들어간다 — 모델이 마커를 그대로 인용했다.

```
프롬프트: 세션 시작 때 주입된 노트가 있으면 마커 코드를 그대로 인용해라.
출력:     PROBE_SESSION_NOTE_7734: 이 문장이 세션 컨텍스트에 주입되었는지 본다.
```

## 이 결과가 받치는 것

`bin/jig-pending-note` — pending 검증 등록부(`probe/PENDING.md`)를 세션 시작 때
자동 표면화하는 훅. 문서 `[D]` 로는 알려져 있었지만, `-p` 경로와 `startup` matcher
조합은 이 실측으로 확정했다.

## 안 잰 것

- `resume` · `clear` matcher 에서의 동작 `[?]` — 확인: settings 의 matcher 만 바꿔
  같은 스크립트 재실행. 현재 설계는 `startup` 만 쓰므로 급하지 않다.
