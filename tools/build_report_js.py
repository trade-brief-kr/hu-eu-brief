#!/usr/bin/env python3
"""헝가리·EU 경제통상 브리프: 일일/주간 JSON 스키마 검증 + file:// 대체본(.js) 생성.

사용법: python3 tools/build_report_js.py [--check PATH] [--check-weekly PATH]
  인자 없음       data/report.json 검증 후 data/report.js 작성 (주간 최신본이 있으면 data/weekly.js도)
  --check         일일 파일만 검증 (쓰기 없음)
  --check-weekly  주간 파일만 검증 (쓰기 없음)
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
SECTION_IDS = ['hu_politics', 'hu_economy', 'eu_policy', 'eu_pubs', 'followup']
SECTION_TITLES = {
    'hu_politics': '① 헝가리 정치·정부',
    'hu_economy': '② 헝가리 경제·산업(기업동향 포함)',
    'eu_policy': '③ EU 경제통상 정책',
    'eu_pubs': '④ EU 발간자료',
    'followup': '⑤ 오늘 확인할 것',
}
WEEKLY_SECTION_IDS = ['hu_politics', 'hu_economy', 'eu_policy', 'eu_pubs']
WEEKLY_SECTION_TITLES = {
    'hu_politics': '정치 및 정부(정책·지원)',
    'hu_economy': '경제 및 산업(기업동향 포함)',
    'eu_policy': 'EU 경제통상 브리핑',
    'eu_pubs': 'EU 주요 발간자료',
}


def require(cond, msg):
    if not cond:
        raise ValueError(msg)


def string(v, path, allow_empty=False):
    require(isinstance(v, str), f'{path}: 문자열이어야 합니다.')
    if not allow_empty:
        require(bool(v.strip()), f'{path}: 비어 있으면 안 됩니다.')


def ymd(v, path):
    string(v, path)
    try:
        require(date.fromisoformat(v).isoformat() == v, f'{path}: YYYY-MM-DD')
    except ValueError:
        raise ValueError(f'{path}: 유효한 YYYY-MM-DD 날짜여야 합니다.') from None


def iso(v, path):
    string(v, path)
    try:
        datetime.fromisoformat(v.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError(f'{path}: ISO 8601 형식이어야 합니다.') from None


def url(v, path):
    if v in (None, ''):
        return
    string(v, path)
    p = urlparse(v)
    require(p.scheme in ('http', 'https') and bool(p.netloc), f'{path}: http(s) URL이어야 합니다.')
    require('utm_source=' not in v, f'{path}: utm_source 파라미터를 제거해야 합니다.')


def bullet(b, path):
    require(isinstance(b, dict), f'{path}: 객체여야 합니다.')
    string(b.get('text'), path + '.text')
    if b.get('url'):
        url(b['url'], path + '.url')
        string(b.get('source'), path + '.source (url이 있으면 매체명 필수)')
    elif 'source' in b:
        string(b['source'], path + '.source', allow_empty=True)
    url(b.get('altUrl'), path + '.altUrl')
    if b.get('altUrl'):
        require(bool(b.get('url')), f'{path}: altUrl은 url과 함께만 사용합니다.')
    if b.get('date'):
        ymd(b['date'], path + '.date')
    if b.get('publishedAt'):
        iso(b['publishedAt'], path + '.publishedAt')


def item(it, path, section_id):
    require(isinstance(it, dict), f'{path}: 객체여야 합니다.')
    string(it.get('tag', ''), path + '.tag', allow_empty=True)
    string(it.get('title', ''), path + '.title', allow_empty=(section_id == 'followup'))
    if section_id != 'followup':
        ymd(it.get('date'), path + '.date')
    elif it.get('date'):
        ymd(it['date'], path + '.date')
    require(isinstance(it.get('korea', False), bool), f'{path}.korea: true/false')
    bs = it.get('bullets')
    require(isinstance(bs, list) and bs, f'{path}.bullets: 1개 이상 필요합니다.')
    for i, b in enumerate(bs):
        bullet(b, f'{path}.bullets[{i}]')
    srcs = it.get('sources', [])
    require(isinstance(srcs, list), f'{path}.sources: 배열이어야 합니다.')
    for i, x in enumerate(srcs):
        require(isinstance(x, dict) and x.get('url'), f'{path}.sources[{i}]: url 필수')
        bullet(dict(x, text='-'), f'{path}.sources[{i}]')
    if section_id != 'followup':
        require(any(b.get('url') for b in bs), f'{path}: 출처 URL이 있는 bullet이 1개 이상 필요합니다(날조 금지·출처 필수).')


def _sections(r, ids):
    secs = r.get('sections')
    require(isinstance(secs, list) and len(secs) == len(ids), f'sections: 정확히 {len(ids)}개여야 합니다.')
    require([s.get('id') for s in secs] == ids, f'sections: id 순서는 {ids} 이어야 합니다.')
    for i, s in enumerate(secs):
        string(s.get('title'), f'sections[{i}].title')
        require(isinstance(s.get('items'), list), f'sections[{i}].items: 배열이어야 합니다.')
        for j, it in enumerate(s['items']):
            item(it, f'sections[{i}].items[{j}]', s['id'])
    require(sum(len(s['items']) for s in secs[:4]) >= 1, 'sections: ①~④에 항목이 1개 이상 필요합니다.')
    notes = r.get('notes', [])
    require(isinstance(notes, list) and all(isinstance(n, str) for n in notes), 'notes: 문자열 배열이어야 합니다.')


def validate(r):
    require(isinstance(r, dict), 'report: 객체여야 합니다.')
    ymd(r.get('date'), 'date')
    iso(r.get('generatedAt'), 'generatedAt')
    string(r.get('coverage'), 'coverage')
    string(r.get('headline'), 'headline')
    _sections(r, SECTION_IDS)
    return r


def validate_weekly(r):
    require(isinstance(r, dict), 'weekly: 객체여야 합니다.')
    ymd(r.get('weekStart'), 'weekStart')
    ymd(r.get('weekEnd'), 'weekEnd')
    ws, we = date.fromisoformat(r['weekStart']), date.fromisoformat(r['weekEnd'])
    require(ws.weekday() == 0, 'weekStart: 월요일이어야 합니다.')
    require((we - ws).days == 6, 'weekEnd: weekStart + 6일(일요일)이어야 합니다.')
    iso(r.get('generatedAt'), 'generatedAt')
    string(r.get('coverage'), 'coverage')
    string(r.get('headline'), 'headline')
    _sections(r, WEEKLY_SECTION_IDS)
    for s in r['sections']:
        for it in s['items']:
            require(r['weekStart'] <= it['date'] <= r['weekEnd'], f"{s['id']}:{it['title']}: date {it['date']}가 주간 범위 밖")
    return r


def js_literal(value):
    return json.dumps(value, ensure_ascii=False, indent=2).replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')


def main(argv):
    try:
        if argv[:1] == ['--check']:
            validate(json.loads(Path(argv[1]).read_text(encoding='utf-8')))
            print('검증 통과:', argv[1])
            return 0
        if argv[:1] == ['--check-weekly']:
            validate_weekly(json.loads(Path(argv[1]).read_text(encoding='utf-8')))
            print('검증 통과(주간):', argv[1])
            return 0
        r = validate(json.loads((ROOT / 'data/report.json').read_text(encoding='utf-8')))
        (ROOT / 'data/report.js').write_text('window.REPORT_DATA = ' + js_literal(r) + ';\n', encoding='utf-8')
        print('data/report.js 작성:', r['date'])
        wp = ROOT / 'data/weekly.json'
        if wp.exists():
            w = validate_weekly(json.loads(wp.read_text(encoding='utf-8')))
            (ROOT / 'data/weekly.js').write_text('window.WEEKLY_DATA = ' + js_literal(w) + ';\n', encoding='utf-8')
            print('data/weekly.js 작성:', w['weekStart'])
        return 0
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        print('검증 실패:', e, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
