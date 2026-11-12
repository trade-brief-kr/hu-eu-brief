#!/usr/bin/env python3
"""data/report.json(일일) 검증 후 게시(최신본 + 보관본 + 색인 + RSS)를 한 번에 처리.

사용법: python3 tools/publish_daily.py [--allow-any-date]
1. data/report.json 검증 (build_report_js.validate와 동일 규칙)
2. date == 오늘(KST) 확인 (--allow-any-date로 생략)
3. data/archive/<date>.json/.js 작성(같은 날짜 재실행 시 덮어씀)
4. data/archive/index.json/.js 재생성(최신순), data/report.js 재생성, feed.xml(RSS, 일일+주간) 재생성
오류 시 아무것도 바꾸지 않음(임시 파일에 쓴 뒤 모두 성공하면 교체). 실패 시 종료 코드 1.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_report_js import ROOT, js_literal, stamp_index, validate  # noqa: E402

KST = timezone(timedelta(hours=9))
DATA = ROOT / 'data'
ARCHIVE = DATA / 'archive'
WEEKLY = DATA / 'weekly'
SITE = 'https://trade-brief-kr.github.io/hu-eu-brief/'
FEED_ITEMS = 40


def titles_of(r):
    return [{'s': s['id'], 'd': it.get('date', ''), 't': it['title']}
            for s in r['sections'] for it in s['items'] if it.get('title')]


def index_entry(r):
    return {'date': r['date'], 'generatedAt': r['generatedAt'],
            'itemCount': sum(len(s['items']) for s in r['sections']), 'titles': titles_of(r)}


def read_index(p):
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []


def feed(daily, weekly):
    rows = [('daily', e) for e in daily] + [('weekly', e) for e in weekly]
    rows.sort(key=lambda x: x[1]['generatedAt'], reverse=True)
    items = []
    for kind, e in rows[:FEED_ITEMS]:
        pub = datetime.fromisoformat(e['generatedAt'].replace('Z', '+00:00'))
        desc = '\n'.join(f"({t['d']}) {t['t']}" for t in e['titles'])
        first = f" · {e['titles'][0]['t']}" if e.get('titles') else ''
        if kind == 'daily':
            title, link, guid = f"[일일] {e['date']}{first}", f"{SITE}?date={e['date']}", f"hu-eu-daily-{e['date']}"
        else:
            title = f"[주간] {e['weekStart']}~{e['weekEnd']}{first}"
            link, guid = f"{SITE}?week={e['weekStart']}#weekly", f"hu-eu-weekly-{e['weekStart']}"
        items.append(f"<item><title>{escape(title)}</title><link>{escape(link)}</link>"
                     f"<guid isPermaLink=\"false\">{guid}</guid><pubDate>{format_datetime(pub)}</pubDate>"
                     f"<description>{escape(desc)}</description></item>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
            '<title>헝가리·EU 경제통상 브리프</title>'
            f'<link>{SITE}</link><description>헝가리 정치·경제와 EU 경제통상 이슈·통계발표 일일·주간 브리핑</description>'
            '<language>ko</language>' + ''.join(items) + '</channel></rss>\n')


def main(argv):
    allow_any = '--allow-any-date' in argv
    staged = []
    try:
        r = validate(json.loads((DATA / 'report.json').read_text(encoding='utf-8')))
        today = datetime.now(KST).date().isoformat()
        if not allow_any and r['date'] != today:
            raise ValueError(f"date: 오늘(KST {today})이 아님: {r['date']} (--allow-any-date로 무시 가능)")
        d = r['date']
        ARCHIVE.mkdir(parents=True, exist_ok=True)
        entries = {d: index_entry(r)}
        for p in sorted(ARCHIVE.glob('????-??-??.json')):
            if p.stem == d:
                continue
            old = validate(json.loads(p.read_text(encoding='utf-8')))
            if old['date'] != p.stem:
                raise ValueError(f'{p.name}: 파일명과 date({old["date"]})가 다름')
            entries[old['date']] = index_entry(old)
        index = sorted(entries.values(), key=lambda e: e['date'], reverse=True)

        def stage(final, text):
            tmp = final.with_name(final.name + '.tmp')
            tmp.write_text(text, encoding='utf-8')
            staged.append((tmp, final))

        body = js_literal(r)
        stage(ARCHIVE / f'{d}.json', json.dumps(r, ensure_ascii=False, indent=2) + '\n')
        stage(ARCHIVE / f'{d}.js', 'window.REPORT_ARCHIVE = window.REPORT_ARCHIVE || {};\n'
              f'window.REPORT_ARCHIVE[{json.dumps(d)}] = {body};\n')
        stage(ARCHIVE / 'index.json', json.dumps(index, ensure_ascii=False, indent=2) + '\n')
        stage(ARCHIVE / 'index.js', 'window.REPORT_INDEX = ' + js_literal(index) + ';\n')
        stage(DATA / 'report.js', 'window.REPORT_DATA = ' + body + ';\n')
        stage(ROOT / 'feed.xml', feed(index, read_index(WEEKLY / 'index.json')))
        for tmp, final in staged:
            tmp.replace(final)
        staged.clear()
        ver = stamp_index()
    except (OSError, ValueError, TypeError, KeyError) as e:
        for tmp, _ in staged:
            tmp.unlink(missing_ok=True)
        print(f'게시 실패(아무 파일도 변경하지 않음): {e}', file=sys.stderr)
        return 1
    print(f'index.html 캐시 버전 v={ver}')
    print(f'게시 완료: {d} (보관 {len(index)}일) → data/report.js, data/archive/{d}.json/.js, index.json/.js, feed.xml')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
