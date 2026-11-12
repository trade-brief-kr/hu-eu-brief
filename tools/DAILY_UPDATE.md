# 일일·주간 업데이트 절차 (헝가리·EU 경제통상 브리프)

독자는 일반 한국인(기업인, 공관·기관 관계자 등). 일일·주간 모두 4개 섹션, headline·오늘 확인할 것 없음.
**에이전트는 직접 웹 조사하지 않는다.** 조사는 ChatGPT 구독 기반 Codex CLI(`codex --search exec`, reasoning high)가 하고,
에이전트는 러너 실행 → 검증 → 게시 → push → 라이브 확인만 한다. 링크 curl 재검증은 기본 OFF(Codex 검증 신뢰).

## A. 일일 (매일 오전 KST 한 번, 주말 포함 가능)
```bash
cd /workspace/hu-eu-brief && git pull --ff-only
bash tools/run_codex_research.sh                 # 결과: data/report.json (검증 통과 시에만 교체), 보통 10~20분
python3 tools/publish_daily.py                   # data/archive/<date>.json/.js + index + report.js + feed.xml
git add -A data feed.xml && git commit -m "Daily brief $(TZ=Asia/Seoul date +%F)" && git push
```
- 확인: https://trade-brief-kr.github.io/hu-eu-brief/data/report.json 의 date가 오늘인지 (Pages 반영 1~2분).

## B. 주간 (매주 월요일 오전 KST, 일일 게시 후)
지난주 월~일(현지 기준) 일일 보관본을 자료로 넣고 Codex가 통합·보완 조사하여 KOTRA 「헝가리 주요이슈 브리핑」 형식으로 작성한다.
```bash
cd /workspace/hu-eu-brief && git pull --ff-only
bash tools/run_codex_research.sh --weekly        # 기본: 지난주 월요일 시작. 결과: data/weekly.json, 보통 15~30분
#   특정 주: bash tools/run_codex_research.sh --weekly --week-start 2026-11-02
python3 tools/publish_weekly.py                  # data/weekly/<weekStart>.json/.js + index + weekly.js + feed.xml
git add -A data feed.xml && git commit -m "Weekly brief $(python3 -c "import json;print(json.load(open('data/weekly.json'))['weekStart'])")" && git push
```
- 확인: https://trade-brief-kr.github.io/hu-eu-brief/data/weekly.json 의 weekStart가 지난주 월요일인지.
- 일일과 주간 러너는 모드별 잠금이라 동시에 돌릴 수 있다(같은 모드 중복 실행만 막음).

## C. 월간 통계 (매월 1일 오전 KST — 일일 절차와 별개, 일일에는 넣지 않음)
「헝가리 주요 통계」 탭(data/stats.json/.js)을 공식·공개 API(Eurostat, BIS, ECB, World Bank, UN Comtrade)에서 다시 받는다. Codex 불필요.
```bash
cd /workspace/hu-eu-brief && git pull --ff-only
python3 tools/fetch_stats.py                     # data/stats.json + data/stats.js 작성, index.html ?v= 갱신. 보통 1~2분
git add data/stats.json data/stats.js index.html && git commit -m "Monthly stats $(TZ=Asia/Seoul date +%F)" && git push
```
- 종료 코드: 0 = 1개 이상 지표 갱신(실패한 지표는 직전 값 유지·stale 표시, errors에 기록) / 1 = 전부 실패(파일 변경 없음 → 커밋하지 않음).
- 확인: https://trade-brief-kr.github.io/hu-eu-brief/data/stats.json 의 generatedAt이 오늘인지, `errors` 배열 확인.
- 통계 갱신 실패는 일일·주간 브리핑과 무관(서로 막지 않음).

## 종료 코드 (run_codex_research.sh, 일일·주간 공통)
0 성공 / 2 환경·사용법(동시 실행, 잘못된 --week-start, 끝나지 않은 주) / 10 Codex 실패 / 11 타임아웃(일일 1800s, 주간 2700s)
/ 12 결과 없음·JSON 오류 / 13 검증 실패 / 14 사전검증 실패.
- 10·11이면 한 번만 재실행. 그 밖의 실패는 게시하지 않고 로그(/tmp/hu-eu-brief-runs/codex-run-<mode>-*/: prompt.md, codex.log,
  raw-*.json, verify-log.json, elapsed_seconds)를 보고.
- 드라이런: `bash tools/run_codex_research.sh --out /tmp/hueu-dry/report.json` (주간: `--weekly --out /tmp/hueu-dry/weekly.json`)
- 프롬프트만 확인: 위에 `--prompt-only` 추가.
- 품질 경고(섹션 0건, 헝가리어 매체 출처 0건, publishedAt 없는 출처)는 verify-log.json warnings에 남고 게시는 막지 않는다.
- publish 스크립트 실패 시 종료 코드 1, 아무 파일도 바뀌지 않는다.

## 알림
게시 후 섹션별 항목 수(정치 및 정부 / 경제 및 산업 / EU 경제통상 이슈 / EU 통계발표)와 대표 항목 제목을 사용자에게 알림
(알림 경로는 운영 에이전트 루틴이 담당). RSS: feed.xml (일일+주간).

## 캐시
- publish_daily.py / publish_weekly.py가 게시 때마다 index.html의 CSS·JS·data/*.js 경로에 `?v=<KST 시각>`을 자동으로 붙인다(브라우저 캐시 무효화).
  app.js는 같은 버전으로 JSON을 `cache: 'no-cache'`로 가져오고, 구 스키마(headline·followup·eu_pubs)는 화면에서 무시한다.

## 규칙 요약
- 수동 정정: data/report.json(또는 data/weekly.json) 수정 후 publish 단계만 다시 실행.
- 조사 규칙은 tools/research_prompt.md (일일·주간 공통, 수정 가능). 스키마는 README와 tools/build_report_js.py.
- 공개 저장소: 개인 실명·직함, 내부 협의 내용 금지.
