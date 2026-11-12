#!/usr/bin/env bash
# 헝가리·EU 경제통상 브리프 조사 러너: ChatGPT(Codex CLI, 웹검색)로 일일 report.json 또는 주간 weekly.json을 작성하고 검증한다.
# 에이전트는 직접 웹 조사하지 않고 이 스크립트만 실행한다. 게시는 하지 않는다.
#
# 사용법: bash tools/run_codex_research.sh [--weekly [--week-start YYYY-MM-DD]] [--out PATH] [--timeout SEC]
#                                          [--check-links] [--keep-work] [--prompt-only]
#   (기본)          일일 모드: 최근 24시간 → data/report.json
#   --weekly        주간 모드: 지난주 월~일(--week-start 월요일 지정 가능) → data/weekly.json
#                   그 주의 data/archive/<날짜>.json 일일본을 자료로 넣고, Codex가 통합·보완 조사한다.
#   --out PATH      검증 통과본을 쓸 위치 (기본 위 경로). 드라이런은 저장소 밖 경로 지정.
#   --timeout SEC   Codex 최대 실행 시간 (기본 일일 1800초, 주간 2700초, 환경변수 CODEX_TIMEOUT)
#   --check-links   (선택) 후처리에서 URL curl 재확인(404/410/DNS만 삭제). 기본 OFF — Codex 검증을 신뢰.
#   --keep-work     Codex 임시 작업 폴더를 지우지 않음
#   --prompt-only   Codex를 실행하지 않고 프롬프트만 <로그폴더>/prompt.md 로 생성 후 종료(0).
#
# 종료 코드 (0일 때만 다음 단계 publish_daily.py / publish_weekly.py 진행)
#   0  성공: 검증 통과본이 --out 에 기록됨
#   2  사용법·환경 오류 (codex 없음, 프롬프트 파일 없음, 동시 실행 중, 잘못된 --week-start)
#   10 Codex 실행 실패 (비정상 종료)
#   11 Codex 타임아웃
#   12 Codex 결과 없음 또는 JSON 파싱 불가
#   13 검증 실패 (날짜 불일치, 스키마 오류, 항목 0건 등)
#   14 publish 스크립트와 동일 규칙의 사전검증 실패
# 실패 시 --out 파일은 변경되지 않는다. 로그: /tmp/hu-eu-brief-runs/codex-run-<모드>-<날짜시각>/ (--out 지정 시 그 폴더)
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE=daily
WEEK_START=""
OUT=""
TIMEOUT="${CODEX_TIMEOUT:-}"
EFFORT="${CODEX_EFFORT:-high}"
CHECK_LINKS=""
KEEP=0
PROMPT_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --weekly) MODE=weekly; shift ;;
    --week-start) WEEK_START="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --check-links) CHECK_LINKS="--check-links"; shift ;;
    --keep-work) KEEP=1; shift ;;
    --prompt-only) PROMPT_ONLY=1; shift ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    *) echo "알 수 없는 옵션: $1" >&2; exit 2 ;;
  esac
done

[ -f "$ROOT/tools/research_prompt.md" ] || { echo "tools/research_prompt.md 없음" >&2; exit 2; }
if [ "$PROMPT_ONLY" != 1 ]; then command -v codex >/dev/null || { echo "codex CLI 없음" >&2; exit 2; }; fi

TODAY="$(TZ=Asia/Seoul date +%F)"
YESTERDAY="$(TZ=Asia/Seoul date -d '-1 day' +%F)"
NOW_ISO="$(TZ=Asia/Seoul date +%Y-%m-%dT%H:%M:%S+09:00)"
NOW_HM="$(TZ=Asia/Seoul date +%H:%M)"
if [ "$MODE" = weekly ]; then
  if [ -z "$WEEK_START" ]; then
    # 지난주 월요일 (오늘이 월요일이면 7일 전)
    DOW=$(TZ=Asia/Seoul date +%u)
    WEEK_START="$(TZ=Asia/Seoul date -d "-$((DOW - 1 + 7)) day" +%F)"
  fi
  [ "$(date -d "$WEEK_START" +%u 2>/dev/null)" = 1 ] || { echo "--week-start는 월요일 YYYY-MM-DD: $WEEK_START" >&2; exit 2; }
  WEEK_END="$(date -d "$WEEK_START +6 day" +%F)"
  [ "$WEEK_END" \< "$TODAY" ] || { echo "주간 범위가 아직 끝나지 않음: $WEEK_START~$WEEK_END" >&2; exit 2; }
  : "${OUT:=$ROOT/data/weekly.json}"; : "${TIMEOUT:=2700}"; FILE=weekly.json; DEFAULT_OUT="$ROOT/data/weekly.json"
else
  : "${OUT:=$ROOT/data/report.json}"; : "${TIMEOUT:=1800}"; FILE=report.json; DEFAULT_OUT="$ROOT/data/report.json"
fi
mkdir -p "$(dirname "$OUT")"
OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"

exec 9>"/tmp/hu-eu-brief-research-$MODE.lock"
flock -n 9 || { echo "다른 조사 러너가 실행 중" >&2; exit 2; }

if [ "$OUT" = "$DEFAULT_OUT" ]; then LOGBASE="/tmp/hu-eu-brief-runs"; else LOGBASE="$(dirname "$OUT")"; fi
LOGDIR="$LOGBASE/codex-run-$MODE-$TODAY-$(TZ=Asia/Seoul date +%H%M%S)"
mkdir -p "$LOGDIR"
WORK="$(mktemp -d /tmp/codex-hueu.XXXXXX)"
cleanup() { [ "$KEEP" = 1 ] || rm -rf "$WORK"; }
trap cleanup EXIT

# 직전 일일 보고서 제목(중복 방지·누락 보완 참고용)
PREV_TITLES="$(python3 - "$ROOT/data/report.json" "$TODAY" <<'PY' 2>/dev/null
import json, sys
try:
    r = json.load(open(sys.argv[1], encoding='utf-8'))
except Exception:
    sys.exit(0)
if r.get('date') == sys.argv[2]:
    sys.exit(0)
print(f"직전 일일 보고서 {r.get('date')} (같은 사안 반복 금지, 새 진전만):")
for s in r.get('sections', []):
    for it in s.get('items', []):
        if it.get('title'):
            print(f"- ({it.get('date','')}) {it['title']}")
PY
)"

# 주간: 그 주의 일일 보관본을 자료로
WEEK_MATERIAL=""
if [ "$MODE" = weekly ]; then
WEEK_MATERIAL="$(python3 - "$ROOT/data/archive" "$WEEK_START" <<'PY'
import json, sys
from datetime import date, timedelta
base, ws = sys.argv[1], date.fromisoformat(sys.argv[2])
found = []
for i in range(7):
    d = (ws + timedelta(days=i)).isoformat()
    try:
        r = json.load(open(f"{base}/{d}.json", encoding='utf-8'))
    except Exception:
        continue
    found.append(d)
    for s in r.get('sections', []):
        for it in s.get('items', []):
            print(json.dumps({'section': s['id'], 'date': it.get('date'), 'title': it.get('title'), 'korea': it.get('korea', False),
                              'bullets': it.get('bullets'), 'sources': it.get('sources', [])}, ensure_ascii=False))
if not found:
    print("(이 주의 일일 보관본 없음 — 전부 직접 조사해 작성)")
else:
    print(f"(일일 보관본 {len(found)}일치: {', '.join(found)} — 빠진 날짜·사안은 직접 조사로 보완)")
PY
)"
fi

# --- 자체완결 프롬프트 구성 ---------------------------------------------------
PROMPT="$LOGDIR/prompt.md"
{
if [ "$MODE" = daily ]; then
cat <<HDR
당신은 한국 독자(기업인, 공관·기관 관계자 등)를 위한 「헝가리·EU 경제통상 브리프」(일일 브리핑)의 조사·작성자다.
웹 검색으로 실제 기사·공식 발표를 찾아 확인하고, 결과를 현재 작업 폴더의 report.json 파일 하나로만 저장한다.
다른 파일은 만들거나 수정하지 않는다. 화면 출력(최종 메시지)은 "DONE" 한 단어로 충분하다.

## 실행 정보
- 오늘(KST): $TODAY, 현재 시각: $NOW_ISO (헝가리·브뤼셀 시각 = KST −8시간, 11~3월 기준)
- 수집 구간: $YESTERDAY $NOW_HM ~ $TODAY $NOW_HM KST (최근 24시간). [누락 보완] 항목만 최대 3일 전까지
  (해당 bullet 맨 앞에 "[누락 보완·MM.DD]" 표기 — 기간 검증용이며 게시본에서는 자동 제거).

## 절대 원칙
1. 지어내지 않는다. 검색으로 확인한 실제 URL·매체·게시 시각만 쓴다.
2. 각 항목의 첫 bullet에는 "source"(매체명), "url"(원문 주소), "publishedAt"(게시 시각, 시간대 포함 ISO 8601)을 넣는다.
   publishedAt은 후처리에서 기간 검증 후 날짜만 남는다. 기간 밖이면 삭제되므로 확실한 것만 쓴다.
3. 출처 URL이 하나도 없는 항목은 삭제된다.
4. 링크 HTTP 재검증은 후처리에서 하지 않는다. 출처·URL 검증은 Codex(본인)가 한다.
5. URL에서 utm_source 등 추적 파라미터를 붙이지 않는다.

$PREV_TITLES

## report.json 스키마 (정확히 이 구조)
{
  "date": "$TODAY",
  "generatedAt": "작성 완료 시각 (예: ${TODAY}T08:10:00+09:00)",
  "coverage": "최근 24시간 발표 중심",
  "sections": [
    {"id":"hu_politics","title":"정치 및 정부","items":[
      {"date":"$YESTERDAY","tag":"","korea":false,"title":"명사형 한국어 제목",
       "bullets":[{"text":"핵심 한 줄(60자 안팎, 명사형 종결).","source":"Portfolio","url":"https://www.portfolio.hu/...","publishedAt":"${YESTERDAY}T14:05:00+01:00"},
                  {"text":"(선택) 영향·다음 단계 한 줄.","source":"Telex","url":"https://telex.hu/...","publishedAt":"${YESTERDAY}T15:20:00+01:00"}]}]},
    {"id":"hu_economy","title":"경제 및 산업","items":[]},
    {"id":"eu_policy","title":"EU 경제통상 이슈","items":[]},
    {"id":"eu_stats","title":"EU 통계발표","items":[
      {"date":"$YESTERDAY","tag":"[Eurostat]","title":"유로지역 10월 소비자물가 속보","bullets":[{"text":"10월 물가상승률 전년 대비 ○.○%(9월 ○.○%), 에너지 ○.○%.","source":"Eurostat","url":"https://ec.europa.eu/eurostat/web/products-euro-indicators/w/...","publishedAt":"${YESTERDAY}T11:00:00+01:00"}]}]}
  ],
  "notes": ["확인하지 못한 점 등 (선택)"]
}
- bullet text에 "ㅇ" 기호는 넣지 않는다(화면에서 붙임). bullet 선택 필드: "altUrl"(재게재 URL, 원문 url과 함께만).
- 각 bullet은 한 문장 60자 안팎. 같은 사안을 다룬 추가 매체는 항목의 선택 필드
  "sources": [{"source":"Index","url":"https://index.hu/...","publishedAt":"…+01:00","altUrl":"(선택)"}] 에 넣는다(자료원 줄에 함께 표시).
- sections는 정확히 4개, 위 id 순서. headline 필드는 쓰지 않는다. 항목이 없으면 "items": [].

## 조사 규칙 (사용자 지정, 그대로 따른다)

HDR
else
cat <<HDR
당신은 한국 독자(기업인, 공관·기관 관계자 등)를 위한 「헝가리·EU 경제통상 브리프」 주간판(KOTRA 부다페스트무역관 「헝가리 주요이슈 브리핑」 형식)의 조사·작성자다.
대상 주간: $WEEK_START(월) ~ $WEEK_END(일), 현지 기준. 아래 "일일 보관본 자료"를 기반으로 하되, 웹 검색으로 그 주의 주요 사안을
직접 확인·보완하여 결과를 현재 작업 폴더의 weekly.json 파일 하나로만 저장한다. 다른 파일은 만들거나 수정하지 않는다.
화면 출력(최종 메시지)은 "DONE" 한 단어로 충분하다.

## 실행 정보
- 오늘(KST): $TODAY, 현재 시각: $NOW_ISO
- 대상: $WEEK_START ~ $WEEK_END 에 발표·보도된 사안만. 항목 date가 범위 밖이면 후처리에서 삭제된다.

## 절대 원칙
1. 지어내지 않는다. 검색으로 확인한 실제 URL·매체·게시 시각만 쓴다. 일일 보관본 항목은 이미 확인된 출처이므로 재사용 가능.
2. 각 항목의 첫 bullet에는 "source", "url"(원문 주소)을 넣고, 게시 시각을 확인했으면 "publishedAt"(시간대 포함 ISO 8601),
   시각은 모르고 게시 날짜만 확인했으면 "date"(YYYY-MM-DD)를 넣는다(주간은 날짜 기준 검증이므로 날짜만으로 충분).
   일일 보관본에서 가져온 출처는 보관본의 "date"를 그대로 쓴다. publishedAt을 추측해 만들지 않는다.
   유료·접속 불가 매체(MLex 등)보다 공식 원문(policy.trade.ec.europa.eu, tron.trade.ec.europa.eu, eur-lex, 정부·기관 사이트)을 url로 우선한다.
3. 출처 URL이 없는 항목은 삭제된다. URL에 utm_source 등 추적 파라미터를 붙이지 않는다.
4. 같은 사안의 여러 날 보도는 하나의 항목으로 묶고, 일일본의 여러 줄은 한 줄 요약으로 압축한다. 추가 매체는 항목의 "sources" 배열에.
5. 주간 핵심 사안이 일일본에 없으면 검색으로 보완한다(특히 KSH 월간 통계, MNB 결정, 정부 주요 결정, EU 무역구제·제재·CBAM, Eurostat·ECB 통계발표).

## 일일 보관본 자료 (JSON lines: section, date, title, korea, bullets)
$WEEK_MATERIAL

## weekly.json 스키마 (정확히 이 구조)
{
  "weekStart": "$WEEK_START",
  "weekEnd": "$WEEK_END",
  "generatedAt": "작성 완료 시각 (예: ${TODAY}T09:00:00+09:00)",
  "coverage": "${WEEK_START//-/.}.~${WEEK_END//-/.}. 주간 누적",
  "sections": [
    {"id":"hu_politics","title":"정치 및 정부","items":[
      {"date":"$WEEK_START","tag":"","korea":false,"title":"명사형 한국어 제목",
       "bullets":[{"text":"이번 주 한 줄 요약(60자 안팎, 명사형 종결).","source":"Népszava","url":"https://nepszava.hu/...","publishedAt":"${WEEK_START}T09:30:00+01:00"},
                  {"text":"(선택) 영향·후속 한 줄.","source":"Magyar Nemzet","url":"https://magyarnemzet.hu/...","date":"$WEEK_START"}]}]},
    {"id":"hu_economy","title":"경제 및 산업","items":[]},
    {"id":"eu_policy","title":"EU 경제통상 이슈","items":[]},
    {"id":"eu_stats","title":"EU 통계발표","items":[]}
  ],
  "notes": ["확인하지 못한 점 등 (선택)"]
}
- 섹션 4개, 위 id 순서. 각 섹션 안 항목은 date 오름차순. headline 필드는 쓰지 않는다.
- 간결 형식: 각 항목 = 제목 + 한 줄 요약 bullet 1개(+ 필요 시 1줄, 각 60자 안팎). 긴 문단 금지.
  같은 사안의 추가 매체는 항목의 선택 필드 "sources": [{"source":"Telex","url":"https://...","date":"YYYY-MM-DD" 또는 "publishedAt":"…"}]에 넣는다.
- bullet text에 "ㅇ" 기호는 넣지 않는다. 선택 필드: "altUrl"(재게재 URL, 원문 url과 함께만).

## 조사 규칙 (사용자 지정, 그대로 따른다. 섹션 이름은 주간 스키마의 것을 쓴다)

HDR
fi
cat "$ROOT/tools/research_prompt.md"
cat <<TAIL

## 검색 체크리스트 (모두 개별 검색한 뒤 작성)
- 헝가리어 매체 최신 기사: portfolio.hu, index.hu, telex.hu, hvg.hu, 444.hu, nepszava.hu, magyarnemzet.hu, vg.hu, mandiner.hu, origo.hu
  (검색어 예: "kormány bejelentette", "Nagy Márton", "KSH infláció", "MNB alapkamat", "akkumulátorgyár", "Samsung SDI Göd", "SK On Iváncsa").
- 영어 매체: hungarytoday.hu, budapesttimes.hu, bbj.hu, dailynewshungary.com, Reuters/Bloomberg/Euronews 헝가리 기사.
- 정부·기관: kormany.hu, ngm.gov.hu(국가경제부), kormany.hu 외교통상부, ksh.hu 속보(Gyorstájékoztató), mnb.hu 보도자료.
- 한국 기업: 삼성SDI·SK온·에코프로비엠·한국타이어·삼성전자·롯데알미늄·솔루스·두산 등 헝가리 공장 뉴스.
- EU: ec.europa.eu/commission/presscorner, policy.trade.ec.europa.eu(무역구제 공지), taxation-customs(CBAM), consilium.europa.eu 보도자료,
  europarl.europa.eu 보도자료, eur-lex 관보, ec.europa.eu/eurostat(euro indicators), ecb.europa.eu, eib.org.

## 마지막 점검 (저장 전에 반드시)
- 날짜·sections 개수(4)·순서·id, JSON 문법 유효. headline·오늘 확인할 것 섹션 없음.
- 각 항목 첫 bullet의 source·url·(publishedAt 또는 date) 재확인. 기간 밖·불확실하면 삭제.
- 한국어 명사형 종결, 헝가리어 원문은 한국어로 번역, 단계(제안/채택/발효/시행) 구분, 내부 업무 지시 표현·내부 인명 없음.
- 현재 작업 폴더에 $FILE 저장 (UTF-8). 다른 파일 생성·수정 금지.
TAIL
} > "$PROMPT"
if [ "$PROMPT_ONLY" = 1 ]; then echo "프롬프트만 생성(Codex 미실행): $PROMPT"; exit 0; fi

# --- Codex 실행 (임시 폴더에서만 쓰기 가능: 저장소 수정 불가) ---
echo "[$(TZ=Asia/Seoul date +%T) KST] Codex $MODE 조사 시작 (최대 ${TIMEOUT}s) work=$WORK log=$LOGDIR"
START=$(date +%s)
# 비밀 환경변수는 Codex에 넘기지 않는다.
for v in $(compgen -e | grep -E '^(DATA_GO_KR|GH_|GITHUB_)|KEY|TOKEN|SECRET|PASSWORD' || true); do unset "$v"; done
timeout --kill-after=60 "$TIMEOUT" codex --search exec -c model_reasoning_effort="\"$EFFORT\"" --skip-git-repo-check --ephemeral \
  -s workspace-write -C "$WORK" -o "$LOGDIR/codex-last-message.txt" - < "$PROMPT" \
  > "$LOGDIR/codex.log" 2>&1
RC=$?
ELAPSED=$(( $(date +%s) - START ))
echo "[$(TZ=Asia/Seoul date +%T) KST] Codex 종료 rc=$RC, ${ELAPSED}s"
echo "$ELAPSED" > "$LOGDIR/elapsed_seconds"
if [ $RC -eq 124 ] || [ $RC -eq 137 ]; then echo "Codex 타임아웃(${TIMEOUT}s)" >&2; exit 11; fi
if [ $RC -ne 0 ]; then echo "Codex 실패 rc=$RC (로그: $LOGDIR/codex.log)" >&2; tail -5 "$LOGDIR/codex.log" >&2; exit 10; fi
if [ ! -s "$WORK/$FILE" ]; then echo "Codex가 $FILE을 만들지 않음" >&2; exit 12; fi
cp "$WORK/$FILE" "$LOGDIR/raw-$FILE"

# --- 후처리 검증 (날짜·스키마·기간; 링크 curl은 기본 OFF) ---
if [ "$MODE" = weekly ]; then
  python3 "$ROOT/tools/verify_report.py" --weekly --week-start "$WEEK_START" --input "$LOGDIR/raw-$FILE" \
    --output "$LOGDIR/verified-$FILE" --log "$LOGDIR/verify-log.json" $CHECK_LINKS
else
  python3 "$ROOT/tools/verify_report.py" --input "$LOGDIR/raw-$FILE" --output "$LOGDIR/verified-$FILE" \
    --log "$LOGDIR/verify-log.json" $CHECK_LINKS
fi
VRC=$?
if [ $VRC -ne 0 ]; then exit $VRC; fi
python3 - "$LOGDIR/verified-$FILE" "$MODE" "$TODAY" "$WEEK_START" "$ROOT/tools" <<'PY' || exit 14
import json, sys
sys.path.insert(0, sys.argv[5])
from build_report_js import validate, validate_weekly
r = json.load(open(sys.argv[1], encoding='utf-8'))
if sys.argv[2] == 'weekly':
    validate_weekly(r)
    assert r['weekStart'] == sys.argv[4], f"weekStart {r['weekStart']} != {sys.argv[4]}"
    print(f"사전검증 통과(게시 안 함): 주간 {r['weekStart']}~{r['weekEnd']}")
else:
    validate(r)
    assert r['date'] == sys.argv[3], f"date {r['date']} != {sys.argv[3]}"
    print(f"사전검증 통과(게시 안 함): {r['date']}")
PY

cp "$LOGDIR/verified-$FILE" "$OUT.tmp" && mv "$OUT.tmp" "$OUT"
if [ "$MODE" = weekly ]; then NEXT="python3 tools/publish_weekly.py"; else NEXT="python3 tools/publish_daily.py"; fi
echo "완료: $OUT (로그 $LOGDIR). 다음 단계: $NEXT"
exit 0
