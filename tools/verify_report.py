#!/usr/bin/env python3
"""Codex가 만든 헝가리·EU 브리프(일일/주간)를 게시 전에 후처리·검증한다 (항목은 지우기만, 만들지 않음).

사용법:
  python3 tools/verify_report.py --input RAW.json --output REPORT.json [--log LOG.json]
                                 [--check-links] [--now ISO] [--window-hours 30]
  python3 tools/verify_report.py --weekly --week-start YYYY-MM-DD --input RAW.json --output WEEKLY.json [--log LOG.json]
처리(일일):
  1. JSON 파싱, date == 오늘(KST) 필수.
  2. 모든 URL에서 utm_* 추적 파라미터 제거.
  3. sections를 hu_politics, hu_economy, eu_policy, eu_pubs, followup 5개 순서로 정규화(제목 기본값).
  4. bullet publishedAt 기간 확인: 기본 30시간(24h+여유). text가 "[누락 보완"으로 시작하면 96시간.
     기간 밖 → 삭제. url은 있는데 source가 없으면 삭제. publishedAt은 bullet "date"(게시 현지 날짜)로 바꿔 남김.
  5. 링크 curl 재검증은 기본 OFF (Codex 검증 신뢰). --check-links 시 404/410/DNS 실패만 삭제.
  6. ①~④ 항목 중 출처 URL bullet이 없는 항목 삭제. 항목 date가 없으면 첫 출처 bullet 날짜로 채움.
  7. build_report_js.validate 스키마 검증.
처리(주간, --weekly): weekStart(월)~weekEnd(일) 범위. 항목 date가 범위 밖이면 삭제,
  bullet publishedAt은 weekStart-3일 ~ weekEnd+1일 허용. validate_weekly 검증.
품질 경고(섹션 0건, 헝가리어 매체 출처 0건 등)는 로그·stderr에만 남기고 실패시키지 않는다.
종료 코드: 0 성공, 12 읽기/JSON 오류, 13 검증 실패. 실패 시 --output은 쓰지 않고 *.rejected.json 남김.
"""
import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_report_js import (SECTION_IDS, SECTION_TITLES, WEEKLY_SECTION_IDS,  # noqa: E402
                             WEEKLY_SECTION_TITLES, validate, validate_weekly)

KST = timezone(timedelta(hours=9))
HU_OUTLETS = ('portfolio', 'index', 'telex', 'hvg', '444', 'népszava', 'nepszava', 'magyar nemzet', 'világgazdaság',
              'vilaggazdasag', 'mandiner', 'origo', 'kormany', 'kormány', 'ksh', 'mnb', 'mti', 'napi.hu', 'g7', 'economx')


def clean_url(u):
    if not isinstance(u, str) or not u.strip():
        return u
    p = urlparse(u.strip())
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith('utm_')]
    return urlunparse(p._replace(query=urlencode(q)))


def parse_ts(v):
    try:
        t = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
        return t if t.tzinfo else None
    except ValueError:
        return None


def link_dead(u):
    try:
        out = subprocess.run(['curl', '-sS', '-o', '/dev/null', '-L', '--max-time', '20', '-A', 'Mozilla/5.0',
                              '-w', '%{http_code}', u], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return False
    code = out.stdout.strip()
    if code in ('404', '410'):
        return True
    return code == '000' and 'resolve' in out.stderr.lower()


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--log')
    ap.add_argument('--check-links', action='store_true')
    ap.add_argument('--now')
    ap.add_argument('--window-hours', type=float, default=30.0)
    ap.add_argument('--weekly', action='store_true')
    ap.add_argument('--week-start')
    a = ap.parse_args(argv)
    now = parse_ts(a.now) if a.now else datetime.now(KST)
    today = now.astimezone(KST).date().isoformat()
    log = {'removed': [], 'warnings': [], 'today': today, 'mode': 'weekly' if a.weekly else 'daily'}

    def finish(code, msg, report=None):
        log['result'] = msg
        if a.log:
            Path(a.log).write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding='utf-8')
        if code == 0:
            Path(a.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print('검증 통과:', msg)
        else:
            if report is not None:
                Path(a.output + '.rejected.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print('검증 실패:', msg, file=sys.stderr)
        for w in log['warnings']:
            print('품질 경고:', w, file=sys.stderr)
        return code

    try:
        r = json.loads(Path(a.input).read_text(encoding='utf-8'))
        assert isinstance(r, dict)
    except Exception as e:  # noqa: BLE001
        return finish(12, f'JSON 읽기 실패: {e}')

    if a.weekly:
        if not a.week_start:
            return finish(13, '--weekly에는 --week-start 필요')
        ws = date.fromisoformat(a.week_start)
        we = ws + timedelta(days=6)
        if r.get('weekStart') != ws.isoformat():
            return finish(13, f"weekStart {r.get('weekStart')} != {ws}", r)
        r['weekEnd'] = we.isoformat()
        ids, titles = WEEKLY_SECTION_IDS, WEEKLY_SECTION_TITLES
        lo_b, hi_b = ws - timedelta(days=3), we + timedelta(days=1)
    else:
        if r.get('date') != today:
            return finish(13, f"date {r.get('date')} != 오늘 {today}", r)
        ids, titles = SECTION_IDS, SECTION_TITLES

    by_id = {s.get('id'): s for s in r.get('sections', []) if isinstance(s, dict)}
    sections = []
    for sid in ids:
        s = by_id.get(sid, {})
        items = []
        for it in s.get('items', []) or []:
            if not isinstance(it, dict):
                continue
            where = f"{sid}:{it.get('title', '')}"
            bullets, extra = [], []
            raw_src = [dict(x, text=x.get('text') or '-', _src=1) for x in (it.get('sources') or []) if isinstance(x, dict)]
            for b in (it.get('bullets', []) or []) + raw_src:
                if not isinstance(b, dict) or not str(b.get('text', '')).strip():
                    continue
                for k in ('url', 'altUrl'):
                    if b.get(k):
                        b[k] = clean_url(b[k])
                    else:
                        b.pop(k, None)
                if b.get('altUrl') and not b.get('url'):
                    b['url'] = b.pop('altUrl')
                if b.get('url') and not str(b.get('source', '')).strip():
                    log['removed'].append({'where': where, 'reason': 'source 없음', 'text': b['text'][:60]})
                    continue
                pub = b.pop('publishedAt', None)
                if pub:
                    t = parse_ts(pub)
                    if t is None:
                        log['removed'].append({'where': where, 'reason': f'publishedAt 형식 오류 {pub}', 'text': b['text'][:60]})
                        continue
                    if a.weekly:
                        bad = not (lo_b <= t.date() <= hi_b)
                    else:
                        hours = 96 if b['text'].lstrip().startswith('[누락 보완') else a.window_hours
                        bad = t < now - timedelta(hours=hours) or t > now + timedelta(hours=2)
                    if bad:
                        log['removed'].append({'where': where, 'reason': f'기간 밖 publishedAt={pub}', 'text': b['text'][:60]})
                        continue
                    b['date'] = t.date().isoformat()
                elif b.get('url') and sid != 'followup' and not b.get('date'):
                    log['warnings'].append(f'{where}: publishedAt·date 없는 출처')
                if a.check_links and b.get('url') and link_dead(b['url']):
                    log['removed'].append({'where': where, 'reason': '링크 404/410/DNS', 'url': b['url']})
                    continue
                if b.pop('_src', None):
                    if b.get('url'):
                        b.pop('text', None)
                        extra.append(b)
                    continue
                if len(b['text']) > 120:
                    log['warnings'].append(f"{where}: bullet {len(b['text'])}자(간결 형식 초과)")
                bullets.append(b)
            if extra:
                it['sources'] = extra
            else:
                it.pop('sources', None)
            if not bullets:
                continue
            if sid != 'followup' and not any(b.get('url') for b in bullets):
                log['removed'].append({'where': where, 'reason': '출처 URL 없는 항목'})
                continue
            it['bullets'] = bullets
            it.setdefault('tag', '')
            it.setdefault('title', '')
            it['korea'] = bool(it.get('korea', False))
            if sid != 'followup' and not it.get('date'):
                d = next((b['date'] for b in bullets if b.get('date')), None)
                if d:
                    it['date'] = d
            if a.weekly and not (ws.isoformat() <= str(it.get('date', '')) <= we.isoformat()):
                log['removed'].append({'where': where, 'reason': f"주간 범위 밖 date={it.get('date')}"})
                continue
            items.append(it)
        if a.weekly or sid != 'followup':
            items.sort(key=lambda x: x.get('date', ''))
        sections.append({'id': sid, 'title': s.get('title') or titles[sid], 'items': items})
    r['sections'] = sections
    r.setdefault('notes', [])

    for s in sections[:4]:
        if not s['items']:
            log['warnings'].append(f"{s['title']} 항목 0건")
    srcs = [b.get('source', '').lower() for s in sections[:2] for it in s['items'] for b in it['bullets'] if b.get('url')]
    if not any(any(h in x for h in HU_OUTLETS) for x in srcs):
        log['warnings'].append('헝가리 현지(헝가리어) 매체·정부 출처 0건')
    try:
        (validate_weekly if a.weekly else validate)(r)
    except (ValueError, KeyError, TypeError) as e:
        return finish(13, str(e), r)
    n = sum(len(s['items']) for s in sections[:4])
    label = f"주간 {r['weekStart']}~{r['weekEnd']}" if a.weekly else r['date']
    return finish(0, f"{label} 항목 {n}건(①~④), 삭제 {len(log['removed'])}건", r)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
