# 헝가리·EU 경제통상 브리프

헝가리 정치·경제(헝가리어 주요 매체·정부·KSH·MNB 발표 포함)와 EU 경제통상 이슈·통계발표를
일일·주간 브리핑으로 정리하는 정적 사이트. 공개 자료만 사용한다. 주간판은 「헝가리 주요이슈 브리핑」 형식
(□ (날짜) 제목 → ㅇ 핵심 한두 줄 → ・ 자료원)을 간결하게 따른다.

- 사이트: https://trade-brief-kr.github.io/hu-eu-brief/
- RSS: https://trade-brief-kr.github.io/hu-eu-brief/feed.xml

## 구성
| 탭 | 내용 |
|---|---|
| 일일 브리핑 | 정치 및 정부 / 경제 및 산업(기업동향·한국기업) / EU 경제통상 이슈 / EU 통계발표. 날짜 이전/다음, 텍스트 복사 |
| 주간 브리핑 | 매주 월요일, 지난주 월~일. 일일과 같은 4개 섹션. 주 단위 이전/다음 |
| 헝가리 주요 통계 | 성장·물가·고용·금리·환율·재정·기본지표·한국–헝가리 교역. 공식 API(Eurostat, BIS, ECB, World Bank, UN Comtrade) 월 1회 자동 수집 (`tools/fetch_stats.py`) |
| 지난 브리핑 검색 | 일일·주간 기사 제목 키워드 검색, 날짜별 목록 |

단순 HTML/CSS/JS(빌드·CDN 없음). `file://`로 열어도 `data/*.js` 대체본으로 동작.

```
index.html, assets/style.css, assets/app.js
data/report.json(.js)          최신 일일본
data/archive/                  일일 보관본 YYYY-MM-DD.json/.js, index.json/.js
data/weekly.json(.js)          최신 주간본
data/weekly/                   주간 보관본 <weekStart>.json/.js, index.json/.js
data/stats.json(.js)           헝가리 주요 통계 (tools/fetch_stats.py, 월 1회)
feed.xml                       RSS (일일+주간)
tools/research_prompt.md       조사 규칙 (Codex 프롬프트에 그대로 포함)
tools/run_codex_research.sh    Codex CLI 조사 러너 (일일 기본, --weekly 주간)
tools/verify_report.py         후처리 검증 (날짜·스키마·기간·utm 제거)
tools/build_report_js.py       스키마 검증 + .js 대체본
tools/publish_daily.py         일일 게시
tools/publish_weekly.py        주간 게시
tools/DAILY_UPDATE.md          일일·주간 절차
```

## 일일 report.json 스키마
```json
{
  "date": "2026-11-12", "generatedAt": "2026-11-12T09:50:00+09:00", "coverage": "최근 24시간 발표 중심",
  "sections": [
    {"id": "hu_politics", "title": "정치 및 정부", "items": [
      {"date": "2026-11-11", "tag": "", "korea": false, "title": "명사형 제목",
       "bullets": [{"text": "…", "source": "Portfolio", "url": "https://…", "date": "2026-11-11", "altUrl": "(선택) 재게재 URL"},
                   {"text": "(선택) 영향·다음 단계 한 줄"}],
       "sources": [{"source": "Telex", "url": "https://…", "date": "2026-11-11"}]}]},
    {"id": "hu_economy", "title": "경제 및 산업", "items": []},
    {"id": "eu_policy", "title": "EU 경제통상 이슈", "items": []},
    {"id": "eu_stats", "title": "EU 통계발표", "items": []}
  ],
  "notes": []
}
```
주간 weekly.json: `weekStart`(월)·`weekEnd`(일) + 같은 형식의 sections 4개(일일과 동일 id·제목), 항목 date는 주간 범위 내.
규칙: bullet은 1~2개·각 한 문장 60자 안팎(120자 초과 시 품질 경고), sources는 선택(추가 매체). headline·오늘 확인할 것 섹션 없음. 모든 항목은 date 필수, 출처 URL bullet 1개 이상, url이 있으면 source 필수, utm_source 금지.

## 절차
`tools/DAILY_UPDATE.md` 참고. 조사는 Codex CLI(ChatGPT 로그인, `codex --search exec`)가 하고, 운영 에이전트는 직접 웹 조사하지 않는다.
