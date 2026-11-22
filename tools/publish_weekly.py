#!/usr/bin/env python3
"""data/weekly.json(주간) 검증 후 게시(최신 주간본 + 주간 보관본 + 주간 색인 + RSS).

사용법: python3 tools/publish_weekly.py [--allow-any-date]
1. data/weekly.json 검증 (build_report_js.validate_weekly: weekStart 월요일, weekEnd=일요일, 항목 date 주간 범위 내)
2. weekEnd < 오늘(KST) 확인 — 끝나지 않은 주는 게시하지 않음 (--allow-any-date로 생략)
3. data/weekly/<weekStart>.json/.js 작성(같은 주 재실행 시 덮어씀)
4. data/weekly/index.json/.js 재생성(최신순), data/weekly.js 재생성, feed.xml(일일+주간) 재생성
오류 시 아무것도 바꾸지 않음. 실패 시 종료 코드 1.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common.brief_common import KST, Stager, js_literal, today_kst  # noqa: E402
from build_report_js import ROOT, stamp_index, validate_weekly  # noqa: E402
from publish_daily import ARCHIVE, DATA, WEEKLY, feed, read_index, titles_of  # noqa: E402


def index_entry(r):
    return {'weekStart': r['weekStart'], 'weekEnd': r['weekEnd'], 'generatedAt': r['generatedAt'],
            'itemCount': sum(len(s['items']) for s in r['sections']), 'titles': titles_of(r)}


def main(argv):
    allow_any = '--allow-any-date' in argv
    stager = Stager()
    try:
        r = validate_weekly(json.loads((DATA / 'weekly.json').read_text(encoding='utf-8')))
        today = today_kst().isoformat()
        if not allow_any and not r['weekEnd'] < today:
            raise ValueError(f"weekEnd {r['weekEnd']}: 아직 끝나지 않은 주 (오늘 KST {today})")
        w = r['weekStart']
        WEEKLY.mkdir(parents=True, exist_ok=True)
        entries = {w: index_entry(r)}
        for p in sorted(WEEKLY.glob('????-??-??.json')):
            if p.stem == w:
                continue
            old = validate_weekly(json.loads(p.read_text(encoding='utf-8')))
            if old['weekStart'] != p.stem:
                raise ValueError(f'{p.name}: 파일명과 weekStart({old["weekStart"]})가 다름')
            entries[old['weekStart']] = index_entry(old)
        index = sorted(entries.values(), key=lambda e: e['weekStart'], reverse=True)

        body = js_literal(r)
        stager.stage(WEEKLY / f'{w}.json', json.dumps(r, ensure_ascii=False, indent=2) + '\n')
        stager.stage(WEEKLY / f'{w}.js', 'window.WEEKLY_ARCHIVE = window.WEEKLY_ARCHIVE || {};\n'
                     f'window.WEEKLY_ARCHIVE[{json.dumps(w)}] = {body};\n')
        stager.stage(WEEKLY / 'index.json', json.dumps(index, ensure_ascii=False, indent=2) + '\n')
        stager.stage(WEEKLY / 'index.js', 'window.WEEKLY_INDEX = ' + js_literal(index) + ';\n')
        latest = index[0]['weekStart']
        latest_body = body if latest == w else js_literal(json.loads((WEEKLY / f'{latest}.json').read_text(encoding='utf-8')))
        latest_r = r if latest == w else json.loads((WEEKLY / f'{latest}.json').read_text(encoding='utf-8'))
        stager.stage(DATA / 'weekly.json', json.dumps(latest_r, ensure_ascii=False, indent=2) + '\n')
        stager.stage(DATA / 'weekly.js', 'window.WEEKLY_DATA = ' + latest_body + ';\n')
        stager.stage(ROOT / 'feed.xml', feed(read_index(ARCHIVE / 'index.json'), index))
        stager.commit()
        ver = stamp_index()
    except (OSError, ValueError, TypeError, KeyError) as e:
        stager.rollback()
        print(f'게시 실패(아무 파일도 변경하지 않음): {e}', file=sys.stderr)
        return 1
    print(f'index.html 캐시 버전 v={ver}')
    print(f'게시 완료: 주간 {w}~{r["weekEnd"]} (보관 {len(index)}주) → data/weekly.json/.js, data/weekly/{w}.json/.js, index.json/.js, feed.xml')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
