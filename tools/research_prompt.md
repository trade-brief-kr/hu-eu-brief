# 헝가리·EU 경제통상 브리프 조사 규칙

이 파일은 헝가리·EU 브리프 전용 조사 기준이다. 필요하면 수정해서 쓴다.
러너(`tools/run_codex_research.sh`, 일일·주간 모두)가 이 파일을 Codex 프롬프트에 그대로 넣는다.

## 목적
헝가리에 관심 있는 한국 독자(기업인, 공관·기관 관계자 등)가 헝가리 정치·경제 동향과 EU 경제통상 이슈·통계발표를 한 화면에서 파악하도록 한다.
형식은 KOTRA 부다페스트무역관 「헝가리 주요이슈 브리핑」의 틀을 따르되 **간결하게** 쓴다:
「□ (YYYY.M.D.) 제목」 → 「ㅇ」 핵심 한 줄 1~2개(명사형 종결) → 「・ 자료원: 매체('YY.M.D.)」.
긴 문단 금지. 읽는 사람이 제목과 한두 줄만 보고 요점을 알 수 있어야 한다.

## 기본 원칙
1. 지어내지 않는다. 웹 검색으로 실제 기사·공식 발표 URL과 게시 시각을 확인한 내용만 쓴다. 기억·추측으로 채우지 않는다.
2. 출처 필수. 각 항목의 첫 bullet에는 반드시 source(매체명), url(기사·발표 원문 주소. 홈페이지·검색결과·태그 페이지 금지),
   publishedAt(게시 시각, 시간대 포함 ISO 8601. 헝가리·EU는 11~3월 +01:00, 4~10월 +02:00)을 넣는다.
   여러 매체를 함께 근거로 쓰면 다음 bullet에도 source·url·publishedAt을 넣는다(자료원에 함께 표시됨).
3. 헝가리어 기사는 한국어로 번역·요약한다. 제목·본문 모두 한국어. 고유명사는 처음에 한글(원어) 병기 가능
   (예: 너지 마르통(Nagy Márton) 국가경제부 장관, 티서당(Tisza)).
4. 명사형 종결(예: "…발표.", "…전망.", "…상황.", "…미확인."). 해석·수식어 최소화, 숫자·통화·기준시점은 기사 그대로.
5. 단계를 구분한다: 제안·발의 / 합의·채택 / 관보 게재·발효 / 시행. 투자는 발표·MOU / 허가 / 착공 / 가동을 섞지 않는다.
6. 한국 관련 우선 표시: 헝가리 내 한국 기업·기관(삼성SDI 괴드, SK온 이반차·코마롬, 에코프로비엠 데브레첸, 한국타이어 라칼마스,
   삼성전자 재스베니, 롯데알미늄·솔루스첨단소재·두산·LG·SK넥실리스 등 배터리 공급망, KOTRA, 주헝가리 한국대사관)과
   한–헝·한–EU 통상 사안은 해당 항목에 "korea": true 를 넣는다. 배터리 공장 환경허가·주민 반대·노동 이슈도 포함.
7. 원 발행 매체 URL 우선. 재게재·요약 사이트(MarketScreener, Yahoo, MSN 등)에서 확인했으면 url=원문, altUrl=재게재.
   원문을 못 찾은 경우에만 재게재 URL을 url에 두고 notes에 "원문 URL 미확인: (매체·제목)".
8. URL에 utm_source 등 추적 파라미터를 붙이지 않는다.
9. 공개 페이지이므로 내부 협의 내용·내부 담당자 실명·미공개 일정은 쓰지 않는다.

## 매체·기관 (모두 확인 대상)
- 헝가리어 주요 매체: Portfolio.hu, Index.hu, Telex.hu, HVG.hu, 444.hu, Népszava, Magyar Nemzet, Világgazdaság(vg.hu),
  Mandiner, Origo (보조: Napi.hu, G7.hu, Economx, MTI/hirado.hu).
  정부 성향(Magyar Nemzet, Mandiner, Origo)과 비판 성향(Telex, 444, HVG, Népszava) 매체를 균형 있게 확인하고,
  정치 쟁점은 가능하면 양쪽 출처를 함께 적는다.
- 영어 매체: Hungary Today, Budapest Times, Budapest Business Journal(bbj.hu), Daily News Hungary, Hungarian Conservative,
  Reuters, Bloomberg, Euronews, Euractiv, Politico Europe, FT.
- 헝가리 정부·기관: kormany.hu(총리실·정부대변인), 국가경제부(Nemzetgazdasági Minisztérium), 외교통상부(KKM, Külgazdasági és
  Külügyminisztérium), 재무부, KSH(중앙통계청, ksh.hu 「Gyorstájékoztató」 속보), MNB(중앙은행, 금리결정·인플레이션 보고서),
  HIPA(투자청), ÁKK(국채관리청), 의회(parlament.hu), Magyar Közlöny(관보).
- EU: ec.europa.eu Press Corner(집행위 발표·IP·STATEMENT), DG TRADE(policy.trade.ec.europa.eu: 무역구제·반덤핑·상계관세·
  세이프가드, FTA), TAXUD(CBAM), 이사회(consilium.europa.eu: 제재 패키지·채택), 유럽의회(europarl.europa.eu 본회의·위원회 표결),
  EU 관보(eur-lex.europa.eu Official Journal L/C 시리즈), Eurostat(euro indicators), ECB, EIB, EU 사법재판소(CJEU), ECA.

## 섹션 구성 (일일·주간 동일 4개, 순서 고정)
독자는 일반 한국인(기업인, 공관·기관 관계자 등)이다. 내부 업무 지시("확인 필요", "담당자" 등) 표현은 쓰지 않는다.
1. 정치 및 정부 (id: hu_politics) — 헝가리 정부 정책·지원제도, 내각·인사, 의회 입법, 선거·여론조사, 대외관계(EU·미국·러시아·중국·우크라이나),
   EU 기금·법치주의 분쟁, 사법·언론. 일일 2~4건.
2. 경제 및 산업 (id: hu_economy) — 헝가리 KSH 통계(GDP·물가·산업생산·고용·임금·소매), MNB 금리·환율(포린트), 재정·국채, 세제,
   에너지(Paks II, 가스·유가), 외국인투자(배터리·EV: BYD 세게드, CATL 데브레첸, BMW 데브레첸, 메르세데스 케치케메트 등),
   한국 기업 동향(korea: true), 부동산·노동시장. 일일 3~5건.
3. EU 경제통상 이슈 (id: eu_policy) — 집행위·이사회·의회 발표: 무역구제(반덤핑·상계관세·세이프가드, 특히 철강·화학·배터리 소재·EV),
   CBAM, 대러 제재, 국가보조금(State Aid) 승인, 산업·에너지·디지털 규제(CRMA, NZIA, 배터리 규정, AI Act 등), FTA·통상협상,
   EU–미국·EU–중국 통상, 한–EU 관련. 정책 보고서·Communication 발표도 여기에. 일일 2~4건.
4. EU 통계발표 (id: eu_stats) — 공식 통계 발표: Eurostat(euro indicators: HICP 물가, GDP, 산업생산, 소매판매, 고용·실업, 교역, 생산자물가 등),
   ECB 통계 발표(통화량·대출, 국제수지, 금리 통계 등), 그 밖의 EU 기관 공식 통계 공표.
   각 항목 = title(지표명·기간, 예: "유로지역 10월 소비자물가 속보") + bullet 1개(핵심 수치: 수준·전월/전년 대비·이전치 비교),
   source=발표기관, url=해당 발표 원문 페이지(데이터베이스 첫 화면 금지). 일일 1~4건, 해당 날짜 발표가 없으면 비워 둔다.

## 항목 형식
- date: 사건·발표 날짜 "YYYY-MM-DD" (현지 기준). PDF의 「□ (YYYY.M.D.)」에 표시된다.
- tag: 선택. "[한국기업]", "[EU–헝가리]", "[통계]", "[무역구제]" 등 짧게. 없으면 "".
- title: 25자 안팎 한국어 명사형 제목(예: "헝가리 중앙은행(MNB), 기준금리 6.5% 동결").
- bullets: 1~2개, 각 bullet은 **한 문장, 60자 안팎(최대 90자)** 핵심 요점. 첫 bullet = 누가·무엇(핵심 사실·수치).
  둘째 bullet(선택) = 영향·조건·다음 단계·미확인 사항. 배경 설명·인용문 나열·여러 문장 문단 금지.
  EU 통계발표는 bullet 1개(핵심 수치 한 줄).
- sources (선택): 같은 사안을 다룬 추가 매체 [{"source","url","publishedAt"(또는 주간에서 보관본 재사용 시 "date")}].
  정치 쟁점은 정부 성향·비판 성향 매체를 함께 넣으면 좋다. 자료원 줄에 bullet 출처와 함께 표시된다.
- korea: 한국 관련이면 true (선택).

## 분량
- 일일: 4개 섹션 합계 8~15건. 24시간 내 확인된 기사가 없으면 억지로 채우지 않는다.
- 주간: 정치 및 정부·경제 및 산업 합계 10~18건, EU 경제통상 이슈 4~8건, EU 통계발표 3~6건. 주간 항목도 일일과 같은 간결 형식(한 줄 요약 1개 + 필요 시 1줄).
- 확인하지 못한 점(사이트 접속 오류, 유료벽 등)은 notes에 짧게 남긴다.
