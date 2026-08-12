#!/usr/bin/env bash
# probe 전용. 훅이 stdin 으로 받은 페이로드를 그대로 적는다.
# 어떤 오류에서도 세션을 막지 않는다 — 항상 exit 0.
log="${1:?사용법: hook.sh <로그경로> [단계]}"
stage="${2:-unknown}"
mkdir -p "$(dirname "$log")" 2>/dev/null || true
{
  printf '=== %s %s\n' "$stage" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  cat
  printf '\n'
} >> "$log" 2>/dev/null || true
exit 0
