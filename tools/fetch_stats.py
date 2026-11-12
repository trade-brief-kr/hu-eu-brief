#!/usr/bin/env python3
"""헝가리 주요 통계: 공식·공개 API에서만 받아 data/stats.json + data/stats.js를 만든다(값을 만들어 넣지 않음).

사용법: python3 tools/fetch_stats.py [--out data/stats.json]
출처:
  Eurostat API  — 실질 GDP 성장률(전기·전년 동기 대비), HICP 물가, 실업률, 산업생산, 재정수지·정부부채
  BIS API       — 헝가리 중앙은행(MNB) 기준금리 (BIS 중앙은행 정책금리 통계)
  ECB Data API  — 유로/포린트 기준환율
  World Bank    — 명목 GDP, 1인당 GDP, 인구
  UN Comtrade   — 한국의 대헝가리 수출·수입 (한국 보고 기준, 공개 preview API)
지표별로 실패하면 직전 data/stats.json의 같은 지표를 유지하고 stale=true, errors에 기록한다(마지막 정상값 유지).
종료 코드: 0 = 1개 이상 갱신(파일 기록), 1 = 전부 실패(파일 변경 없음).
"""
import csv
import io
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
UA = {'User-Agent': 'hu-eu-brief-stats/1.0 (+https://trade-brief-kr.github.io/hu-eu-brief/)'}
ESTAT = 'https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data'


def get(url, timeout=40, retries=2):
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode('utf-8')
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 + 2 * i)
    raise RuntimeError(f'{type(last).__name__}: {str(last)[:120]}')


def num(v):
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def now_iso():
    return datetime.now(KST).isoformat(timespec='seconds')


def estat(dataset, params, n):
    q = urllib.parse.urlencode(dict(params, geo='HU'))
    d = json.loads(get(f'{ESTAT}/{dataset}?{q}'))
    inv = {v: k for k, v in d['dimension']['time']['category']['index'].items()}
    vals = d.get('value', {})
    pts = [(inv[int(k)], float(v)) for k, v in sorted(vals.items(), key=lambda kv: int(kv[0])) if v is not None]
    if not pts:
        raise RuntimeError('관측값 없음')
    return pts[-n:], d.get('updated')


def ind(id_, group, label, unit, pts, source, url, updated=None, note='', decimals=1, freq=''):
    last, prev = pts[-1], (pts[-2] if len(pts) > 1 else None)
    return {'id': id_, 'group': group, 'label': label, 'unit': unit, 'decimals': decimals, 'freq': freq,
            'period': last[0], 'value': last[1],
            'prevPeriod': prev[0] if prev else None, 'prevValue': prev[1] if prev else None,
            'series': [[p, v] for p, v in pts], 'source': source, 'sourceUrl': url,
            'sourceUpdated': updated, 'fetchedAt': now_iso(), 'note': note}


def estat_url(ds):
    return f'https://ec.europa.eu/eurostat/databrowser/view/{ds}/default/table?lang=en'


def f_estat(id_, group, label, unit, ds, params, n, note='', freq=''):
    def run():
        pts, up = estat(ds, params, n)
        return ind(id_, group, label, unit, pts, f'Eurostat ({ds})', estat_url(ds), up, note, freq=freq)
    return run


def f_bis():
    text = get('https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.HU?lastNObservations=800&format=csv')
    rows = [(r['TIME_PERIOD'], float(r['OBS_VALUE'])) for r in csv.DictReader(io.StringIO(text)) if num(r.get('OBS_VALUE'))]
    if not rows:
        raise RuntimeError('관측값 없음')
    rows.sort()
    # 금리 변경 이력: 값이 바뀐 날만 남겨 직전 금리와 비교
    changes = [rows[0]]
    for p, v in rows[1:]:
        if v != changes[-1][1]:
            changes.append((p, v))
    monthly = {}
    for p, v in rows:
        monthly[p[:7]] = v
    series = sorted(monthly.items())[-24:]
    last = rows[-1]
    out = ind('base_rate', 'finance', '기준금리 (헝가리 중앙은행)', '%', series, 'BIS 중앙은행 정책금리 (원자료: MNB)',
              'https://data.bis.org/topics/CBPOL', None, '', decimals=2, freq='D')
    out['period'], out['value'] = last[0], last[1]
    if len(changes) > 1:
        out['prevPeriod'], out['prevValue'] = f'{changes[-1][0]} 변경 전', changes[-2][1]
        out['note'] = f'{changes[-1][0]}부터 {changes[-1][1]:g}% 적용(직전 {changes[-2][1]:g}%). BIS 집계 기준일까지 반영'
    else:
        out['prevPeriod'], out['prevValue'] = None, None
        out['note'] = f'{changes[-1][0]} 이후 변동 없음'
    out['seriesNote'] = '월말 기준'
    return out


def f_ecb():
    text = get('https://data-api.ecb.europa.eu/service/data/EXR/D.HUF.EUR.SP00.A?lastNObservations=400&format=csvdata')
    rows = sorted((r['TIME_PERIOD'], float(r['OBS_VALUE'])) for r in csv.DictReader(io.StringIO(text)) if num(r.get('OBS_VALUE')))
    if not rows:
        raise RuntimeError('관측값 없음')
    monthly = {}
    for p, v in rows:
        monthly[p[:7]] = v
    out = ind('eur_huf', 'finance', '유로/포린트 환율 (ECB 기준환율)', '포린트/유로', sorted(monthly.items())[-13:],
              'ECB Data Portal (EXR.D.HUF.EUR.SP00.A)', 'https://data.ecb.europa.eu/data/datasets/EXR/EXR.D.HUF.EUR.SP00.A',
              None, '숫자가 클수록 포린트 약세', decimals=2, freq='D')
    out['period'], out['value'] = rows[-1]
    out['prevPeriod'], out['prevValue'] = rows[-2] if len(rows) > 1 else (None, None)
    out['seriesNote'] = '월말 기준'
    return out


def f_wb(id_, label, unit, code, scale, decimals):
    def run():
        d = json.loads(get(f'https://api.worldbank.org/v2/country/HUN/indicator/{code}?format=json&per_page=12'))
        pts = sorted((x['date'], x['value'] / scale) for x in d[1] if x.get('value') is not None)
        if not pts:
            raise RuntimeError('관측값 없음')
        return ind(id_, 'basic', label, unit, pts[-10:], f'World Bank WDI ({code})',
                   f'https://data.worldbank.org/indicator/{code}?locations=HU', d[0].get('lastupdated'), decimals=decimals, freq='A')
    return run


COMTRADE = 'https://comtradeapi.un.org/public/v1'


def comtrade(freq, period):
    q = urllib.parse.urlencode({'reporterCode': 410, 'partnerCode': 348, 'period': period, 'flowCode': 'X,M',
                                'cmdCode': 'TOTAL', 'customsCode': 'C00', 'motCode': 0, 'partner2Code': 0})
    d = json.loads(get(f'{COMTRADE}/preview/C/{freq}/HS?{q}', timeout=60))
    if d.get('error'):
        raise RuntimeError(str(d['error'])[:120])
    out = {}
    for r in d.get('data', []):
        if r.get('flowCode') in ('X', 'M') and r.get('primaryValue') is not None:
            out[r['flowCode']] = float(r['primaryValue'])
    time.sleep(1.5)
    return out


def f_trade():
    da = json.loads(get(f'{COMTRADE}/getDA/C/A/HS?reporterCode=410'))
    last_year = max(int(r['period']) for r in da.get('data', []) if r.get('period'))
    years = []
    for y in range(last_year - 4, last_year + 1):
        v = comtrade('A', str(y))
        if 'X' in v and 'M' in v:
            years.append((str(y), v['X'] / 1e8, v['M'] / 1e8))
    if not years:
        raise RuntimeError('연간 교역 데이터 없음')
    url = 'https://comtradeplus.un.org/'
    src = 'UN Comtrade (한국 보고 기준)'
    note = '한국 기준 통관 통계(UN Comtrade), 억 달러'
    exp = ind('kr_export', 'trade', '한국의 대헝가리 수출 (연간)', '억 달러', [(y, x) for y, x, _ in years], src, url, None, note, freq='A')
    imp = ind('kr_import', 'trade', '한국의 대헝가리 수입 (연간)', '억 달러', [(y, m) for y, _, m in years], src, url, None, note, freq='A')
    bal = ind('kr_balance', 'trade', '한국의 대헝가리 무역수지 (연간)', '억 달러', [(y, x - m) for y, x, m in years], src, url, None, note, freq='A')
    return [exp, imp, bal]


TASKS = [
    ('gdp_qoq', f_estat('gdp_qoq', 'growth', '실질 GDP 성장률 (전기 대비)', '%', 'namq_10_gdp',
                        {'unit': 'CLV_PCH_PRE', 's_adj': 'SCA', 'na_item': 'B1GQ', 'sinceTimePeriod': '2022-Q1'}, 12,
                        '계절·근무일 조정', 'Q')),
    ('gdp_yoy', f_estat('gdp_yoy', 'growth', '실질 GDP 성장률 (전년 동기 대비)', '%', 'namq_10_gdp',
                        {'unit': 'CLV_PCH_SM', 's_adj': 'SCA', 'na_item': 'B1GQ', 'sinceTimePeriod': '2022-Q1'}, 12,
                        '계절·근무일 조정', 'Q')),
    ('hicp', f_estat('hicp', 'prices', '소비자물가 상승률 (전년 동월 대비)', '%', 'prc_hicp_minr',
                     {'unit': 'RCH_A', 'coicop18': 'TOTAL', 'sinceTimePeriod': '2024-01'}, 24,
                     'EU 기준 통합소비자물가지수(HICP) 기준', 'M')),
    ('unemployment', f_estat('unemployment', 'prices', '실업률', '%', 'une_rt_m',
                             {'s_adj': 'SA', 'age': 'TOTAL', 'sex': 'T', 'unit': 'PC_ACT', 'sinceTimePeriod': '2024-01'}, 24,
                             '15~74세, 계절조정', 'M')),
    ('industry', f_estat('industry', 'growth', '산업생산 증가율 (전년 동월 대비)', '%', 'sts_inpr_m',
                         {'nace_r2': 'B-D', 's_adj': 'CA', 'unit': 'PCH_SM', 'sinceTimePeriod': '2024-01'}, 24,
                         '광업·제조업·전기가스(건설 제외), 근무일 조정', 'M')),
    ('deficit', f_estat('deficit', 'fiscal', '재정수지 (GDP 대비)', '%', 'gov_10dd_edpt1',
                        {'na_item': 'B9', 'sector': 'S13', 'unit': 'PC_GDP', 'sinceTimePeriod': '2016'}, 10,
                        '일반정부, 음수는 적자', 'A')),
    ('debt', f_estat('debt', 'fiscal', '정부부채 (GDP 대비)', '%', 'gov_10q_ggdebt',
                     {'na_item': 'GD', 'sector': 'S13', 'unit': 'PC_GDP', 'sinceTimePeriod': '2022-Q1'}, 12,
                     '일반정부 총부채(마스트리히트 기준), 분기', 'Q')),
    ('base_rate', f_bis),
    ('eur_huf', f_ecb),
    ('gdp_usd', f_wb('gdp_usd', '명목 GDP', '억 달러', 'NY.GDP.MKTP.CD', 1e8, 0)),
    ('gdp_pc', f_wb('gdp_pc', '1인당 GDP', '달러', 'NY.GDP.PCAP.CD', 1, 0)),
    ('population', f_wb('population', '인구', '만 명', 'SP.POP.TOTL', 1e4, 1)),
    ('trade', f_trade),
]
ORDER = ['gdp_qoq', 'gdp_yoy', 'hicp', 'unemployment', 'industry', 'base_rate', 'eur_huf', 'deficit', 'debt',
         'gdp_usd', 'gdp_pc', 'population', 'kr_export', 'kr_import', 'kr_balance']
GROUPS = {'growth': '성장·생산', 'prices': '물가·고용', 'finance': '금리·환율', 'fiscal': '재정',
          'basic': '기본 지표', 'trade': '한국–헝가리 교역'}


def main(argv):
    out = Path(argv[argv.index('--out') + 1]) if '--out' in argv else ROOT / 'data/stats.json'
    try:
        old = {i['id']: i for i in json.loads(out.read_text(encoding='utf-8')).get('indicators', [])}
    except (OSError, ValueError):
        old = {}
    got, errors, ok = {}, [], 0
    for name, fn in TASKS:
        try:
            res = fn()
            for r in (res if isinstance(res, list) else [res]):
                got[r['id']] = r
            ok += 1
            print(f'OK   {name}')
        except Exception as e:  # noqa: BLE001
            errors.append({'task': name, 'error': str(e)[:200], 'at': now_iso()})
            print(f'FAIL {name}: {e}', file=sys.stderr)
    if not ok:
        print('전부 실패: 파일을 바꾸지 않음', file=sys.stderr)
        return 1
    inds = []
    for i in ORDER:
        if i in got:
            inds.append(got[i])
        elif i in old:
            inds.append(dict(old[i], stale=True))
    data = {'generatedAt': now_iso(), 'country': '헝가리', 'groups': GROUPS, 'indicators': inds, 'errors': errors}
    body = json.dumps(data, ensure_ascii=False, indent=2)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + '.tmp')
    tmp.write_text(body + '\n', encoding='utf-8')
    tmp.replace(out)
    js = out.with_suffix('.js')
    js.write_text('window.STATS_DATA = ' + body.replace('\u2028', '\\u2028').replace('\u2029', '\\u2029') + ';\n', encoding='utf-8')
    print(f'작성: {out} / {js} (지표 {len(inds)}개, 실패 작업 {len(errors)}개)')
    if out.resolve() == (ROOT / 'data/stats.json').resolve():
        sys.path.insert(0, str(ROOT / 'tools'))
        from build_report_js import stamp_index
        print('index.html 캐시 버전:', stamp_index())
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
