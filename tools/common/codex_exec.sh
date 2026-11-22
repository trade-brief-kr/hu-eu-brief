#!/usr/bin/env bash

brief_scrub_secrets() {
  local v
  for v in $(compgen -e | grep -E '^(DATA_GO_KR|GH_|GITHUB_)|KEY|TOKEN|SECRET|PASSWORD' || true); do unset "$v"; done
}

# brief_deadline_text TIMEOUT [MARGIN]
brief_deadline_text() {
  local timeout_seconds="${1/#./0.}" margin="${2:-420}"
  TZ=Asia/Seoul date -d "now +$timeout_seconds seconds -$margin seconds" +%H:%M
}

brief_time_budget_prompt() {
  local duration="$1" result_file="$2" seconds minutes deadline
  # GNU timeout accepts fractional seconds and optional duration suffixes.
  read -r seconds minutes < <(LC_ALL=C awk -v duration="$duration" 'BEGIN {
    unit = substr(duration, length(duration))
    scale = 1
    if (unit == "m") scale = 60
    if (unit == "h") scale = 3600
    if (unit == "d") scale = 86400
    seconds = duration * scale
    printf "%.9f %.6g\n", seconds, seconds / 60
  }')
  deadline="$(brief_deadline_text "$seconds")"
  cat <<EOF

## 시간 규칙 (반드시)
- 마감: 오늘 $deadline KST (\`TZ=Asia/Seoul date +%H:%M\` 으로 수시 확인). 전체 제한 ${minutes}분.
- 조사 초반(첫 번째 섹션을 채운 직후) 현재까지 확인된 내용으로 $result_file 초안을 먼저 저장하고, 이후 섹션마다 덮어써 갱신한다(항상 유효한 JSON 유지).
- 열리지 않거나 응답이 느린 사이트(15초 이상, 접속 오류·403·캡차)는 한 번만 시도하고 바로 다른 출처로 넘어간다. 같은 사이트 재시도 금지.
- 마감 10분 전이 되면 새 검색을 멈추고, 이미 확인한 자료로 마무리·점검 후 저장한다. 빈 섹션은 notes에 "시간 내 확인 못함"으로 남긴다.
EOF
}

# brief_codex_run WORK PROMPT LOGDIR TIMEOUT EFFORT [RESULT_FILE [MODE [elapsed-first]]]
brief_codex_run() {
  local work="$1" prompt="$2" logdir="$3" timeout_seconds="$4" effort="$5"
  local result_file="${6:-report.json}" mode="${7:-}" elapsed_order="${8:-}"
  local start rc elapsed
  BRIEF_SALVAGED=0

  echo "[$(TZ=Asia/Seoul date +%T) KST] Codex ${mode:+$mode }조사 시작 (최대 ${timeout_seconds}s) work=$work log=$logdir"
  start=$(date +%s)
  brief_scrub_secrets
  rc=0
  timeout --kill-after=60 "$timeout_seconds" codex --search exec -c model_reasoning_effort="\"$effort\"" --skip-git-repo-check --ephemeral \
    -s workspace-write -C "$work" -o "$logdir/codex-last-message.txt" - < "$prompt" \
    > "$logdir/codex.log" 2>&1 || rc=$?
  elapsed=$(( $(date +%s) - start ))
  if [ "$elapsed_order" = elapsed-first ]; then
    echo "$elapsed" > "$logdir/elapsed_seconds"
  fi
  echo "[$(TZ=Asia/Seoul date +%T) KST] Codex 종료 rc=$rc, ${elapsed}s"
  if [ "$elapsed_order" != elapsed-first ]; then
    echo "$elapsed" > "$logdir/elapsed_seconds"
  fi

  if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then
    if [ "${BRIEF_SALVAGE_ON_TIMEOUT:-1}" = 1 ] && [ -f "$work/$result_file" ] &&
      python3 -c 'import json, sys
with open(sys.argv[1], encoding="utf-8") as result:
    json.load(result)' "$work/$result_file" >/dev/null 2>&1; then
      BRIEF_SALVAGED=1
      echo "타임아웃이지만 작성된 결과를 회수해 검증 진행" >> "$logdir/codex.log"
      echo "Codex 타임아웃 — 작성된 결과를 회수해 검증 진행"
      return 0
    fi
    echo "Codex 타임아웃(${timeout_seconds}s)" >&2
    return 11
  fi
  if [ "$rc" -ne 0 ]; then
    echo "Codex 실패 rc=$rc (로그: $logdir/codex.log)" >&2
    tail -5 "$logdir/codex.log" >&2
    return 10
  fi
  if [ ! -s "$work/$result_file" ]; then
    echo "Codex가 $result_file을 만들지 않음" >&2
    return 12
  fi
  return 0
}
