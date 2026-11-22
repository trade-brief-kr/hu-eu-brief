"""Shared helpers for building, verifying, and publishing briefs."""

import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


KST = timezone(timedelta(hours=9))
ASSET_RE = re.compile(r'(href|src)="((?:assets|data)/[^"?]+\.(?:css|js))(\?v=[^"]*)?"')


def now_kst():
    return datetime.now(KST)


def today_kst():
    return now_kst().date()


def js_literal(value):
    return json.dumps(value, ensure_ascii=False, indent=2).replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')


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
    return code in ('404', '410') or (code == '000' and 'resolve' in out.stderr.lower())


def stamp_index(root, version=None, *, asset_re=ASSET_RE, missing_ok=True):
    """Stamp asset paths in index.html and return the version."""
    version = version or now_kst().strftime('%Y%m%d%H%M%S')
    p = root / 'index.html'
    if missing_ok and not p.exists():
        return version
    text = p.read_text(encoding='utf-8')
    new = asset_re.sub(lambda m: f'{m.group(1)}="{m.group(2)}?v={version}"', text)
    if new != text:
        p.write_text(new, encoding='utf-8')
    return version


class Stager:
    """Write temporary files before replacing the publication files in order."""

    def __init__(self):
        self._staged = []

    def stage(self, final, text):
        tmp = final.with_name(final.name + '.tmp')
        tmp.write_text(text, encoding='utf-8')
        self._staged.append((tmp, final))

    def commit(self):
        for tmp, final in self._staged:
            tmp.replace(final)
        self._staged.clear()

    def rollback(self):
        for tmp, _ in self._staged:
            tmp.unlink(missing_ok=True)
        self._staged.clear()
