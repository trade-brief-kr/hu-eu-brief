(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var tabs = ['daily', 'weekly', 'search'], active = 'daily', hits = [], flashTimer;
  var names = {
    hu_politics: '정치 및 정부', hu_economy: '경제 및 산업',
    eu_policy: 'EU 경제통상 이슈', eu_stats: 'EU 통계발표'
  };
  var ORDER = ['hu_politics', 'hu_economy', 'eu_policy', 'eu_stats'];
  var VER = (function () {
    var el = document.currentScript || document.querySelector('script[src*="assets/app.js"]');
    var m = el && /[?&]v=([\w.-]+)/.exec(el.getAttribute('src') || '');
    return m ? m[1] : String(Math.floor(Date.now() / 60000));
  }());
  function bust(path) { return path + (path.indexOf('?') < 0 ? '?' : '&') + 'v=' + encodeURIComponent(VER); }
  // 구 스키마(headline, followup, eu_pubs)가 캐시·보관본에 남아 있어도 4개 섹션만 그린다.
  function normalize(r) {
    if (!r || !Array.isArray(r.sections)) return r;
    var by = {};
    r.sections.forEach(function (s) { if (s && s.id) by[s.id === 'eu_pubs' ? 'eu_stats' : s.id] = s; });
    var out = {};
    Object.keys(r).forEach(function (k) { if (k !== 'headline') out[k] = r[k]; });
    out.sections = ORDER.map(function (id) {
      var s = by[id] || {};
      return { id: id, title: names[id], items: Array.isArray(s.items) ? s.items.filter(function (it) { return it && it.title; }) : [] };
    });
    return out;
  }
  function sectionTitle(s) { return names[s.id] || s.title || s.id; }
  function bucket() { return { latest: null, report: null, index: [], cache: {}, ready: false, token: 0, request: '', error: '' }; }
  var state = { daily: bucket(), weekly: bucket() };
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function safeUrl(s) {
    if (typeof s !== 'string' || !/^https?:\/\//i.test(s) || /[\u0000-\u0020\u007f]/.test(s)) return '';
    try { var u = new URL(s); return u.hostname && /^https?:$/.test(u.protocol) ? s : ''; } catch (e) { return ''; }
  }
  function validDate(d) { return /^\d{4}-\d{2}-\d{2}$/.test(d || '') && !isNaN(Date.parse(d)); }
  function date(d) { var p = (d || '').split('-'); return p.length === 3 ? p[0] + '.' + Number(p[1]) + '.' + Number(p[2]) + '.' : ''; }
  function shortDate(d) { return date(d).replace(/^\d{2}/, "'"); }
  function range(r, compact) {
    var end = date(r.weekEnd);
    if (compact && r.weekEnd && r.weekStart.slice(0, 4) === r.weekEnd.slice(0, 4)) end = end.slice(5);
    return date(r.weekStart) + '~' + end;
  }
  function hm(iso) {
    // Convert offsets and UTC to KST rather than relabelling the input time.
    var value = String(iso || '');
    var d = new Date(value + (/T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(value) ? '+09:00' : ''));
    if (isNaN(d.getTime())) return '--:--';
    d = new Date(d.getTime() + 9 * 3600000);
    return ('0' + d.getUTCHours()).slice(-2) + ':' + ('0' + d.getUTCMinutes()).slice(-2);
  }
  function key(kind, r) { return r ? r[kind === 'daily' ? 'date' : 'weekStart'] : ''; }
  function label(kind, r) { return kind === 'daily' ? date(r.date) : range(r, true); }
  function title(kind, r) {
    return kind === 'daily' ? '헝가리·EU 일일 브리핑 (' + date(r.date) + ')' : '헝가리 주요이슈 브리핑 (' + range(r) + ')';
  }
  function sources(it) {
    var out = [];
    (it.bullets || []).concat(it.sources || []).forEach(function (s) {
      if (!safeUrl(s.url)) return;
      var old = out.filter(function (x) { return x.url === s.url; })[0];
      if (old) { if (!old.altUrl && safeUrl(s.altUrl)) old.altUrl = s.altUrl; return; }
      out.push({ source: s.source || '원문', url: s.url, date: s.date || it.date, altUrl: safeUrl(s.altUrl) });
    });
    return out;
  }
  function sourceLabel(s) { return s.source + (s.date ? '(' + shortDate(s.date) + ')' : ''); }
  function sourceHtml(it) {
    var ss = sources(it);
    return ss.length ? '<p class="sources">・ 자료원: ' + ss.map(function (s) {
      return '<a href="' + esc(s.url) + '" target="_blank" rel="noopener noreferrer">' + esc(sourceLabel(s)) + '</a>' +
        (s.altUrl ? '<a class="src-alt" href="' + esc(s.altUrl) + '" target="_blank" rel="noopener noreferrer">「재게재」</a>' : '');
    }).join(', ') + '</p>' : '';
  }
  function itemId(kind, s, n) { return kind + '-' + s + '-' + n; }
  function itemHtml(it, section, n, kind) {
    var h = '<article class="item' + (it.korea === true ? ' korea-item' : '') + '" id="' + esc(itemId(kind, section, n)) + '" tabindex="-1">';
    h += '<h3>□ (' + esc(date(it.date)) + ') ' + esc(it.title) +
      (it.tag ? '<span class="chip">' + esc(it.tag) + '</span>' : '') +
      (it.korea === true ? '<span class="korea-badge">한국 관련</span>' : '') + '</h3>';
    h += '<ul>' + (it.bullets || []).map(function (b) { return '<li class="bullet">' + esc(b.text) + '</li>'; }).join('') + '</ul>';
    return h + sourceHtml(it) + '</article>';
  }
  function render(kind) {
    var c = state[kind], r = c.report, h = '';
    $(kind).setAttribute('aria-busy', String(!c.ready || !!c.request));
    if (!r) {
      h = c.error || (!c.ready || c.request ? '브리핑을 불러오고 있습니다.' : kind === 'weekly' ? '주간 브리핑이 아직 없습니다' : '일일 브리핑이 아직 없습니다');
      $(kind).innerHTML = '<div class="card"><p class="empty" role="status">' + esc(h) + '</p></div>';
    } else {
      r.sections.forEach(function (s) {
        h += '<section class="card sec section-' + esc(s.id) + '"><h2>' + esc(sectionTitle(s)) + '</h2>';
        h += s.items.length ? s.items.map(function (it, n) { return itemHtml(it, s.id, n, kind); }).join('') : '<p class="empty">확인된 항목 없음</p>';
        h += '</section>';
      });
      if (r.notes && r.notes.length) h += '<aside class="notes"><h2>수집 참고</h2><ul>' + r.notes.map(function (n) { return '<li>· ' + esc(n) + '</li>'; }).join('') + '</ul></aside>';
      $(kind).innerHTML = h;
    }
    updateNav(kind); updateChrome();
  }
  function updateNav(kind) {
    var c = state[kind], week = kind === 'weekly', sel = $(week ? 'archive-week' : 'archive-date');
    var current = key(kind, c.report), idx = c.index.slice();
    if (current && !idx.some(function (e) { return key(kind, e) === current; })) idx.push(c.report);
    idx.sort(function (a, b) { return key(kind, b).localeCompare(key(kind, a)); });
    sel.innerHTML = idx.length ? idx.map(function (e, i) {
      return '<option value="' + esc(key(kind, e)) + '">' + esc(label(kind, e)) + (i === 0 ? ' (최신)' : '') + '</option>';
    }).join('') : '<option value="">보고서 없음</option>';
    sel.value = current;
    sel.disabled = !c.ready || !!c.request || !idx.length;
    var pos = c.index.map(function (e) { return key(kind, e); }).indexOf(current);
    $(week ? 'prev-week' : 'prev-day').disabled = !!c.request || pos < 0 || pos >= c.index.length - 1;
    $(week ? 'next-week' : 'next-day').disabled = !!c.request || pos <= 0;
  }
  function updateChrome() {
    var search = active === 'search', c = search ? null : state[active], r = c && c.report;
    $('controls').hidden = search;
    $('daily-nav').hidden = active !== 'daily'; $('weekly-nav').hidden = active !== 'weekly';
    $('copy').hidden = search; $('copy').disabled = !r || !!(c && c.request);
    $('report-title').textContent = search ? '지난 브리핑 검색' : r ? title(active, r) : active === 'weekly' ? '헝가리 주요이슈 브리핑' : '헝가리·EU 일일 브리핑';
    $('updated').textContent = search ? '일일·주간 브리핑 아카이브' : r ? '확인시각 ' + hm(r.generatedAt) + ' KST｜' + r.coverage : '';
    var latestKey = c && (key(active, c.latest) || (c.index[0] && key(active, c.index[0])));
    $('archive-banner').hidden = search || !latestKey || (!r ? !c.error : key(active, r) === latestKey);
    $('archive-banner-text').textContent = r ? label(active, r) + ' 지난 보고서를 보고 있습니다.' : '요청한 보고서를 불러오지 못했습니다.';
    document.title = $('report-title').textContent + ' | 헝가리·EU 경제통상 브리프';
  }
  function syncUrl() {
    var u = new URL(location.href); u.hash = active === 'daily' ? '' : active;
    ['daily', 'weekly'].forEach(function (kind) {
      var c = state[kind], k = key(kind, c.report), p = kind === 'daily' ? 'date' : 'week';
      if (!c.ready || c.request || !k) return;
      if (k === key(kind, c.latest)) u.searchParams.delete(p); else u.searchParams.set(p, k);
    });
    try { history.replaceState(null, '', u.href); } catch (e) { /* file:// browsers may restrict history */ }
  }
  function selectTab(kind, write) {
    active = tabs.indexOf(kind) < 0 ? 'daily' : kind;
    tabs.forEach(function (t) {
      $(t + '-tab').setAttribute('aria-selected', String(t === active));
      $(t + '-tab').tabIndex = t === active ? 0 : -1; $(t).hidden = t !== active;
    });
    updateChrome(); if (write) syncUrl();
  }
  function fetchJson(path) {
    return Promise.resolve().then(function () { return fetch(bust(path), { cache: 'no-cache' }); }).then(function (r) {
      if (!r.ok) throw new Error(r.status); return r.json();
    });
  }
  function loadScript(src) {
    return new Promise(function (ok, fail) {
      var s = document.createElement('script'); s.src = bust(src);
      s.onload = function () { s.remove(); ok(); }; s.onerror = function () { s.remove(); fail(new Error('없음')); };
      document.head.appendChild(s);
    });
  }
  function read(path, getFallback) {
    return fetchJson(path + '.json').catch(function () {
      var cached = getFallback();
      return cached != null ? cached : loadScript(path + '.js').then(getFallback);
    });
  }
  function loadReport(kind, d) {
    var c = state[kind];
    if (!validDate(d)) return Promise.reject(new Error('날짜 오류'));
    if (key(kind, c.latest) === d) return Promise.resolve(c.latest);
    if (c.cache[d]) return Promise.resolve(c.cache[d]);
    return read('data/' + (kind === 'daily' ? 'archive/' : 'weekly/') + d, function () {
      return (window[kind === 'daily' ? 'REPORT_ARCHIVE' : 'WEEKLY_ARCHIVE'] || {})[d];
    }).then(function (r) {
      if (!r || key(kind, r) !== d || !Array.isArray(r.sections)) throw new Error('보고서 없음');
      r = normalize(r); c.cache[d] = r; return r;
    });
  }
  function scrollHit(kind, r, hit) {
    if (!hit) return;
    var target;
    r.sections.some(function (s) {
      if (s.id !== hit.s) return false;
      return s.items.some(function (it, n) {
        if (it.title !== hit.t || (hit.d && it.date !== hit.d)) return false;
        target = $(itemId(kind, s.id, n)); return true;
      });
    });
    if (target) { target.focus({ preventScroll: true }); target.scrollIntoView({ block: 'start' }); }
  }
  function show(kind, d, write, hit) {
    var c = state[kind], token = ++c.token; c.request = d; c.error = ''; render(kind);
    return loadReport(kind, d).then(function (r) {
      if (token !== c.token) return;
      c.request = ''; c.report = r; render(kind); if (write) syncUrl();
      if (active === kind) scrollHit(kind, r, hit);
    }).catch(function () {
      if (token !== c.token) return;
      c.request = ''; c.error = date(d) + ' 보고서를 불러오지 못했습니다.'; render(kind); flash(c.error);
    });
  }
  function step(kind, delta) {
    var c = state[kind], pos = c.index.map(function (e) { return key(kind, e); }).indexOf(key(kind, c.report));
    if (pos >= 0 && c.index[pos + delta]) show(kind, key(kind, c.index[pos + delta]), true);
  }
  function reportHref(kind, d) {
    var u = new URL(location.href); u.search = ''; u.searchParams.set(kind === 'daily' ? 'date' : 'week', d);
    u.hash = kind === 'weekly' ? 'weekly' : ''; return u.href;
  }
  function searchLink(kind, entry, hit) {
    var n = hits.push({ kind: kind, d: key(kind, entry), hit: hit }) - 1;
    var meta = '<span class="type-badge">[' + (kind === 'daily' ? '일일' : '주간') + ']</span>' + esc(label(kind, entry));
    return '<li><a href="' + esc(reportHref(kind, key(kind, entry))) + '" data-result="' + n + '">' +
      (hit ? '<span class="result-meta">' + meta + ' · ' + esc(names[hit.s] || hit.s) + '</span><span class="result-title">' +
        esc('□ (' + date(hit.d) + ') ' + hit.t) + '</span>' : meta) + '</a></li>';
  }
  function renderSearch() {
    var q = $('search-query').value.trim().toLowerCase(), h = '', count = 0; hits = [];
    ['daily', 'weekly'].forEach(function (kind) {
      var entries = state[kind].index, list = '';
      entries.forEach(function (e) {
        if (!q) { list += searchLink(kind, e); return; }
        (e.titles || []).forEach(function (t) {
          if ((t.t || '').toLowerCase().indexOf(q) >= 0) { list += searchLink(kind, e, t); count++; }
        });
      });
      if (list || !q) h += '<section class="card"><h2>' + (kind === 'daily' ? '일일 브리핑' : '주간 브리핑') + '</h2>' +
        (list ? '<ul class="' + (q ? 'result-list' : 'archive-list') + '">' + list + '</ul>' : '<p class="empty">' +
          (!state[kind].ready ? '목록을 불러오고 있습니다.' : kind === 'weekly' ? '주간 브리핑이 아직 없습니다' : '등록된 브리핑이 없습니다') + '</p>') + '</section>';
    });
    $('search-count').textContent = q ? '검색 결과 ' + count + '건' : '전체 일일 ' + state.daily.index.length + '건 · 주간 ' + state.weekly.index.length + '건';
    $('search-results').innerHTML = h || '<div class="card"><p class="empty">검색 결과가 없습니다.</p></div>';
  }
  function copyText(kind) {
    var r = state[kind].report; if (!r) return '';
    var out = [title(kind, r)];
    if (kind === 'daily') out.push('확인시각 ' + hm(r.generatedAt) + ' KST｜' + r.coverage);
    out.push('');
    r.sections.forEach(function (s) {
      out.push(sectionTitle(s));
      if (!s.items.length) out.push('확인된 항목 없음', '');
      s.items.forEach(function (it) {
        out.push('□ (' + date(it.date) + ') ' + it.title + (it.tag ? ' ' + it.tag : '') + (it.korea === true ? ' [한국 관련]' : ''));
        (it.bullets || []).forEach(function (b) { out.push(' ㅇ ' + b.text); });
        var ss = sources(it);
        if (ss.length) out.push(' ・ 자료원: ' + ss.map(function (x) {
          return sourceLabel(x) + ' ' + x.url + (x.altUrl ? ' 「재게재」 ' + x.altUrl : '');
        }).join(', '));
        out.push('');
      });
    });
    if (r.notes && r.notes.length) out.push('수집 참고', r.notes.map(function (n) { return '· ' + n; }).join('\n'));
    return out.join('\n').trim();
  }
  function flash(msg) { clearTimeout(flashTimer); $('status').textContent = msg; flashTimer = setTimeout(function () { $('status').textContent = ''; }, 3500); }
  function doCopy() {
    if (active === 'search' || !state[active].report) return;
    var text = copyText(active), done = function () { flash('브리핑 텍스트를 복사했습니다.'); };
    function fallback() {
      var focus = document.activeElement, ta = document.createElement('textarea'); ta.value = text;
      ta.style.cssText = 'position:fixed;top:0;left:-9999px'; ta.setAttribute('aria-label', '복사할 브리핑 텍스트');
      document.body.appendChild(ta); ta.select();
      try { if (!document.execCommand('copy')) throw new Error('복사 실패'); done(); }
      catch (e) { flash('복사하지 못했습니다. 본문을 선택해 복사해 주세요.'); }
      ta.remove(); if (focus) focus.focus({ preventScroll: true });
    }
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done, fallback); else fallback();
  }
  function readUrl() {
    selectTab(location.hash === '#search' ? 'search' : location.hash === '#weekly' ? 'weekly' : 'daily', false);
    var u = new URL(location.href);
    ['daily', 'weekly'].forEach(function (kind) {
      var c = state[kind], d = u.searchParams.get(kind === 'daily' ? 'date' : 'week') || key(kind, c.latest);
      if (c.ready && d && d !== key(kind, c.report) && d !== c.request) show(kind, d, false);
    });
  }
  function initData(kind) {
    var c = state[kind], week = kind === 'weekly', prefix = week ? 'WEEKLY' : 'REPORT';
    return Promise.all([
      read('data/' + (week ? 'weekly' : 'report'), function () { return window[prefix + '_DATA']; }).catch(function () { return null; }),
      read('data/' + (week ? 'weekly' : 'archive') + '/index', function () { return window[prefix + '_INDEX']; }).catch(function () { return []; })
    ]).then(function (res) {
      res[0] = normalize(res[0]);
      c.latest = res[0] && Array.isArray(res[0].sections) && validDate(key(kind, res[0])) ? res[0] : null;
      c.index = (Array.isArray(res[1]) ? res[1] : []).filter(function (e, i, all) {
        return e && validDate(key(kind, e)) && all.map(function (x) { return key(kind, x); }).indexOf(key(kind, e)) === i;
      });
      if (c.latest && !c.index.some(function (e) { return key(kind, e) === key(kind, c.latest); })) {
        var entry = { date: c.latest.date, weekStart: c.latest.weekStart, weekEnd: c.latest.weekEnd, titles: [] };
        c.latest.sections.forEach(function (s) { s.items.forEach(function (it) { entry.titles.push({ s: s.id, d: it.date, t: it.title }); }); });
        c.index.push(entry);
      }
      c.index.sort(function (a, b) { return key(kind, b).localeCompare(key(kind, a)); }); c.ready = true;
      var want = new URL(location.href).searchParams.get(week ? 'week' : 'date') || key(kind, c.latest) || (c.index[0] && key(kind, c.index[0]));
      c.report = want === key(kind, c.latest) ? c.latest : null;
      render(kind); renderSearch();
      if (want && !c.report) return show(kind, want, false);
    });
  }
  function init() {
    tabs.forEach(function (t) { $(t + '-tab').addEventListener('click', function () { selectTab(t, true); }); });
    $('tabs').addEventListener('keydown', function (e) {
      var n = tabs.indexOf(active);
      if (e.key === 'ArrowRight') n = (n + 1) % 3;
      else if (e.key === 'ArrowLeft') n = (n + 2) % 3;
      else if (e.key === 'Home') n = 0; else if (e.key === 'End') n = 2; else return;
      e.preventDefault(); selectTab(tabs[n], true); $(tabs[n] + '-tab').focus();
    });
    ['daily', 'weekly'].forEach(function (kind) {
      var suffix = kind === 'daily' ? 'day' : 'week';
      $('prev-' + suffix).addEventListener('click', function () { step(kind, 1); });
      $('next-' + suffix).addEventListener('click', function () { step(kind, -1); });
      $(kind === 'daily' ? 'archive-date' : 'archive-week').addEventListener('change', function (e) { show(kind, e.target.value, true); });
    });
    $('to-latest').addEventListener('click', function () {
      var c = state[active]; if (c) show(active, key(active, c.latest) || (c.index[0] && key(active, c.index[0])), true);
    });
    $('copy').addEventListener('click', doCopy); $('search-query').addEventListener('input', renderSearch);
    $('search-results').addEventListener('click', function (e) {
      var el = e.target;
      while (el && el !== this && !el.hasAttribute('data-result')) el = el.parentNode;
      if (!el || el === this || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || e.button > 0) return;
      var hit = hits[Number(el.getAttribute('data-result'))]; if (!hit) return;
      e.preventDefault(); selectTab(hit.kind, false);
      show(hit.kind, hit.d, true, hit.hit).then(function () { if (!hit.hit || !hit.hit.s) $('main').scrollIntoView({ block: 'start' }); });
    });
    window.addEventListener('hashchange', readUrl); window.addEventListener('popstate', readUrl);
    readUrl(); initData('daily'); initData('weekly');
  }
  document.addEventListener('DOMContentLoaded', init);
}());
