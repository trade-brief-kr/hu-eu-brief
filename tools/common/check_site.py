#!/usr/bin/env python3
"""Check one brief site and report the result without modifying it."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone
from html.parser import HTMLParser
from http.client import HTTPException
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import socket
import subprocess
import tempfile
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, unquote_plus, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


KST = timezone(timedelta(hours=9), "KST")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
NETWORK_ERRORS = (OSError, HTTPException, ValueError, OverflowError)
ASSET_SUFFIXES = set(
    ".css .js .mjs .cjs .json .jsonld .webmanifest .xml .rss .atom .map .wasm "
    ".png .jpg .jpeg .gif .svg .ico .webp .avif .bmp .tif .tiff .apng "
    ".woff .woff2 .ttf .otf .eot .mp3 .wav .ogg .m4a .mp4 .webm .vtt .pdf".split()
)
SOURCE_TAGS = {"script", "img", "source", "audio", "video", "track", "embed", "input", "iframe"}
ASSET_RELS = {"stylesheet", "icon", "apple-touch-icon", "mask-icon", "manifest", "preload", "modulepreload", "prefetch"}
BROWSER_NAMES = ("google-chrome", "chromium", "chromium-browser")
RENDER_TIMEOUT = 30
PNG_HEADER = b"\x89PNG\r\n\x1a\n"


class PreserveHead(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme not in {"http", "https"}:
            raise HTTPError(req.full_url, code, msg, headers, fp)
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and req.get_method() == "HEAD":
            redirected.method = "HEAD"
        return redirected


OPENER = build_opener(PreserveHead())


def origin(parts):
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("HTTP(S) URL required")
    default_port = 443 if parts.scheme == "https" else 80
    return parts.scheme, parts.hostname, default_port if parts.port is None else parts.port


def public_url(url):
    """Report the endpoint without credentials, query values, or fragments."""
    try:
        parts = urlsplit(url)
        origin(parts)
        host = parts.netloc.rsplit("@", 1)[-1]
        path = quote(parts.path, safe="/%:@!$&'()*+,;=-._~")
        return urlunsplit((parts.scheme, host, path, "", ""))
    except ValueError:
        return "잘못된 URL"


def network_code(error):
    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, socket.gaierror):
        return "DNS"
    if isinstance(reason, (str, OSError)):
        message = str(reason).lower()
        if "name or service not known" in message or "nodename" in message:
            return "DNS"
    return "네트워크 오류"


def fetch(url, timeout, *, method="GET", read=False, ranged=False):
    headers = {"User-Agent": USER_AGENT}
    if ranged:
        headers["Range"] = "bytes=0-0"
    try:
        request = Request(url, headers=headers, method=method)
        with OPENER.open(request, timeout=timeout) as response:
            body = response.read() if read else None
            return response.status, body, response.geturl()
    except HTTPError as error:
        error.close()
        return error.code, None, url
    except NETWORK_ERRORS as error:
        return network_code(error), None, url


class IndexReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.base = None
        self.references = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "base":
            if self.base is None:
                self.base = attributes.get("href")
            return
        rels = (attributes.get("rel") or "").lower().split()
        for attribute in ("href", "src"):
            value = (attributes.get(attribute) or "").strip()
            if not value or value.startswith("#"):
                continue
            asset_tag = (attribute == "src" and tag in SOURCE_TAGS) or (
                attribute == "href" and tag == "link" and ASSET_RELS.intersection(rels)
            )
            self.references.append((value, asset_tag))


def index_assets(html, index_url):
    parser = IndexReferences()
    parser.feed(html)
    parser.close()
    index_origin = origin(urlsplit(index_url))
    base_url = index_url
    if parser.base:
        try:
            candidate = urljoin(index_url, parser.base)
            origin(urlsplit(candidate))
            base_url = candidate
        except ValueError:
            pass

    assets = set()
    stamps = set()
    for reference, asset_tag in parser.references:
        try:
            parts = urlsplit(urljoin(base_url, reference))
            if origin(parts) != index_origin or parts.username is not None:
                continue
        except ValueError:
            continue
        stamps.update(value for key, value in parse_qsl(parts.query) if key == "v")
        if not asset_tag and PurePosixPath(parts.path).suffix.lower() not in ASSET_SUFFIXES:
            continue
        query = "&".join(
            field for field in parts.query.split("&") if unquote_plus(field.partition("=")[0]) != "v"
        )
        assets.add(urlunsplit(parts._replace(query=query, fragment="")))
    return sorted(assets), sorted(stamps)


def article_urls(report):
    pending = [report]
    urls = set()
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            for key, value in item.items():
                if isinstance(value, (list, dict)):
                    pending.append(value)
                elif key in {"url", "altUrl"} and isinstance(value, str):
                    url = value.strip()
                    if url.lower().startswith(("http://", "https://")):
                        urls.add(url)
        elif isinstance(item, list):
            pending.extend(item)
    return sorted(urls)


def check_link(url, timeout):
    code, _, _ = fetch(url, timeout, method="HEAD")
    if isinstance(code, str) or code in {403, 405, 501}:
        # Closing the GET response after its headers avoids downloading a full article.
        code, _, _ = fetch(url, timeout, ranged=True)
    if isinstance(code, int) and 200 <= code < 400:
        status = "ok"
    elif code in {404, 410, "DNS"}:
        status = "broken"
    else:
        status = "unverifiable"
    return {"url": public_url(url), "code": code, "status": status}


def check_report(args, now, result):
    code, body, _ = fetch(args.report_url, args.timeout, read=True)
    if code != 200:
        result["errors"].append(f"보고서 GET 실패 ({code})")
        return None
    try:
        report = json.loads(body)
    except (ValueError, RecursionError):
        result["errors"].append("보고서 JSON 파싱 실패")
        return None
    report_date = report.get(args.date_key) if isinstance(report, dict) else None
    if not isinstance(report_date, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", report_date):
        result["errors"].append("보고서 날짜 누락 또는 형식 오류")
        return None
    result["date"] = report_date
    if report_date == result["today"]:
        return report

    yesterday = (now.date() - timedelta(days=1)).isoformat()
    scheduled = datetime.combine(now.date(), args.expect_by or time.min, KST)
    before_schedule = args.expect_by is not None and now < scheduled
    within_lag = args.lag_hours > 0 and (now - scheduled).total_seconds() / 3600 <= args.lag_hours
    if report_date == yesterday and (before_schedule or within_lag):
        result["warnings"].append("게시 유예 시간 내 어제 보고서")
        return None
    result["errors"].append(f"보고서 날짜 불일치 (기대 {result['today']}, 실제 {report_date})")
    return None


# 새 프로필로 처음 실행하면 Chrome이 멈추는 일이 있어 고정 프로필을 재사용하고, 시간 초과 시 한 번 더 시도한다.
CHROME_PROFILE = Path(os.environ.get("BRIEF_CHROME_PROFILE") or Path.home() / ".cache" / "brief-health-chrome")


def render_chromium(browser, url, screenshot, profile):
    # 사이트별 프로필(병렬 실행 시 프로필 잠금 충돌 방지)
    profile.mkdir(parents=True, exist_ok=True)
    try:
        return _render_chromium_once(browser, url, screenshot, profile)
    except subprocess.TimeoutExpired:
        return _render_chromium_once(browser, url, screenshot, profile)


def _render_chromium_once(browser, url, screenshot, profile):
    command = [
        browser, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
        "--window-size=1280,2000", "--virtual-time-budget=8000", "--disable-background-networking",
        f"--user-data-dir={profile}",
        f"--screenshot={screenshot}", "--dump-dom", url,
    ]
    with subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True,
    ) as process:
        try:
            dom, _ = process.communicate(timeout=RENDER_TIMEOUT)
            if process.returncode:
                raise subprocess.CalledProcessError(process.returncode, command)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            # Chromium starts child processes that can otherwise outlive the timeout.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            raise
    return dom.decode("utf-8", errors="replace")


def render_playwright(playwright, timeout_error, url, screenshot, date_strings):
    with playwright() as runner:
        browser_type = runner.chromium
        if not Path(browser_type.executable_path).is_file():
            return None
        deadline = monotonic() + RENDER_TIMEOUT

        def remaining_ms(limit=RENDER_TIMEOUT):
            return max(1, int(min(limit, deadline - monotonic()) * 1000))

        with browser_type.launch(channel="chromium", timeout=remaining_ms()) as browser:
            context = browser.new_context(viewport={"width": 1280, "height": 2000}, service_workers="block")
            context.route("**/*", lambda route: (
                route.continue_() if route.request.method in {"GET", "HEAD"} else route.abort()
            ))
            if hasattr(context, "route_web_socket"):
                context.route_web_socket("**/*", lambda socket_route: socket_route.close())
            page = context.new_page()
            page.goto(url, timeout=remaining_ms())
            try:
                page.wait_for_function(
                    "dates => dates.some(date => document.body?.innerText.includes(date))",
                    arg=date_strings, timeout=remaining_ms(8),
                )
            except timeout_error:
                pass
            page.screenshot(path=screenshot, timeout=remaining_ms())
            return page.content()


def check_render(args, day):
    if args.screenshot == "off":
        return {"status": "skipped", "reason": "옵션 off"}
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout, sync_playwright
    except ImportError:
        sync_playwright = None
    browser = next((path for name in BROWSER_NAMES if (path := shutil.which(name))), None)
    if sync_playwright is None and browser is None:
        return {"status": "skipped", "reason": "브라우저 없음"}

    directory = Path("/tmp/brief-health")
    filename = re.sub(r"[^\w-]", "_", args.name)[:60] or "site"
    destination = directory / f"{filename}-{day.isoformat()}.png"
    dates = [
        day.isoformat(), f"{day.month}월 {day.day}일", day.strftime("%Y.%m.%d"),
        f"{day.year}.{day.month}.{day.day}", f"{day.year}. {day.month}. {day.day}.",
    ]
    try:
        directory.mkdir(mode=0o700, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as temp_dir:
            screenshot = Path(temp_dir) / "capture.png"
            dom = None
            if sync_playwright is not None:
                dom = render_playwright(sync_playwright, PlaywrightTimeout, args.site, screenshot, dates)
            if dom is None and browser is not None:
                dom = render_chromium(browser, args.site, screenshot, CHROME_PROFILE / filename)
            if dom is None:
                return {"status": "skipped", "reason": "브라우저 없음"}
            if not screenshot.is_file() or screenshot.stat().st_size < 10 * 1024:
                return {"status": "fail", "reason": "PNG 누락 또는 10KB 미만"}
            with screenshot.open("rb") as png:
                if png.read(len(PNG_HEADER)) != PNG_HEADER:
                    return {"status": "fail", "reason": "PNG 형식 오류"}
            screenshot.replace(destination)
    except subprocess.TimeoutExpired:
        # 브라우저 자체 문제일 수 있어 실패가 아니라 확인 불가(경고)로 둔다.
        return {"status": "warn", "reason": "브라우저 시간 초과(렌더 확인 불가)"}
    except subprocess.CalledProcessError as error:
        return {"status": "fail", "reason": f"브라우저 비정상 종료 ({error.returncode})"}
    except Exception as error:
        # Browser error messages can include the full URLs of loaded resources.
        if sync_playwright is not None and isinstance(error, PlaywrightTimeout):
            return {"status": "warn", "reason": "브라우저 시간 초과(렌더 확인 불가)"}
        return {"status": "fail", "reason": "브라우저 실행 또는 화면 저장 실패"}

    if not any(date in dom for date in dates):
        return {"status": "warn", "reason": "렌더된 DOM에 오늘 날짜 없음", "path": str(destination)}
    return {"status": "ok", "path": str(destination)}


def check_site(args):
    start = monotonic()
    now = datetime.now(KST)
    result = {
        "name": args.name, "site": public_url(args.site), "status": "OK",
        "today": now.date().isoformat(), "date": None, "version_stamps": [],
        "assets": {"total": 0, "failed": []},
        "links": {"status": "skipped", "ok": 0, "unverifiable": 0, "broken": 0, "broken_links": []},
        "errors": [], "warnings": [],
    }
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        index = pool.submit(fetch, args.site, args.timeout, read=True)
        report = check_report(args, now, result)
        code, body, final_url = index.result()
        asset_checks = []
        if code == 200:
            assets, stamps = index_assets(body.decode("utf-8", errors="replace"), final_url)
            result["version_stamps"] = stamps
            result["assets"]["total"] = len(assets)
            asset_checks = [(url, pool.submit(fetch, url, args.timeout)) for url in assets]
        else:
            result["errors"].append(f"인덱스 GET 실패 ({code})")

        if not args.no_links and report is not None:
            result["links"]["status"] = "checked"
            for link in pool.map(lambda url: check_link(url, args.timeout), article_urls(report)):
                status = link["status"]
                result["links"][status] += 1
                if status == "broken":
                    result["links"]["broken_links"].append(link)
        for url, task in asset_checks:
            code, _, _ = task.result()
            if code != 200:
                result["assets"]["failed"].append({"url": public_url(url), "code": code})

    render = check_render(args, now.date())
    result["render"] = render
    if render["status"] == "warn":
        result["warnings"].append(render["reason"])
    if result["errors"] or result["assets"]["failed"] or result["links"]["broken"] or render["status"] == "fail":
        result["status"] = "FAIL"
    result["elapsed_seconds"] = round(monotonic() - start, 2)
    return result


def print_summary(result):
    assets = result["assets"]
    links = result["links"]
    render = result["render"]
    link_counts = f"ok {links['ok']}/unverifiable {links['unverifiable']}/broken {links['broken']}"
    if links["status"] == "skipped":
        link_counts += " (건너뜀)"
    stamps = ", ".join(json.dumps(stamp, ensure_ascii=False) for stamp in result["version_stamps"])
    summary = [
        f"{result['name']} {result['status']}", f"날짜 {result['date'] or '-'}",
        f"자산 {assets['total']}개", f"링크 {link_counts}", f"렌더 {render['status']}",
        f"{result['elapsed_seconds']:.2f}초",
    ]
    if stamps:
        summary.append(f"버전 {stamps}")
    if result["warnings"]:
        summary.append("경고 " + ", ".join(result["warnings"]))
    print(" | ".join(summary))
    for error in result["errors"]:
        print(f"  {error}")
    for asset in assets["failed"]:
        print(f"  자산 실패 {asset['url']} ({asset['code']})")
    for link in links["broken_links"]:
        print(f"  깨진 링크 {link['url']} ({link['code']})")
    if render["status"] == "fail":
        print(f"  렌더 실패 {render['reason']}")


def expect_by(value):
    if re.fullmatch(r"[0-9]{2}:[0-9]{2}", value):
        try:
            return time.fromisoformat(value)
        except ValueError:
            pass
    raise argparse.ArgumentTypeError("게시 예정 시각은 HH:MM 형식이어야 합니다")


def parse_args():
    parser = argparse.ArgumentParser(description="브리프 사이트 상태 점검")
    parser.add_argument("--site", required=True, metavar="URL")
    parser.add_argument("--name")
    parser.add_argument("--lag-hours", type=float, default=0, help="게시 예정 시각(기본 KST 자정) 이후 유예 시간")
    parser.add_argument("--expect-by", type=expect_by, metavar="HH:MM", help="게시 예정 시각(KST)")
    parser.add_argument("--report-path", default="data/report.json")
    parser.add_argument("--date-key", default="date")
    parser.add_argument("--no-links", action="store_true")
    parser.add_argument("--screenshot", choices=("auto", "off", "on"), default="auto")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    if not math.isfinite(args.lag_hours) or args.lag_hours < 0:
        parser.error("--lag-hours는 0 이상의 유한한 값이어야 합니다")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout은 0보다 큰 유한한 값이어야 합니다")
    if args.workers < 1:
        parser.error("--workers는 1 이상이어야 합니다")

    try:
        site = urlsplit(args.site)
        site_origin = origin(site)
        if site.username is not None or site.query or site.fragment:
            raise ValueError
    except ValueError:
        parser.error("--site에 자격 증명, 쿼리, 프래그먼트가 없는 HTTP(S) URL을 지정해야 합니다")
    args.site = urlunsplit(site._replace(path=site.path.rstrip("/") + "/"))
    args.name = args.name or site.hostname
    try:
        report = urlsplit(args.report_path)
        if report.scheme or report.netloc or report.fragment or not report.path.lstrip("/"):
            raise ValueError
        args.report_url = urljoin(args.site, args.report_path.lstrip("/"))
        if origin(urlsplit(args.report_url)) != site_origin:
            raise ValueError
    except ValueError:
        parser.error("--report-path는 사이트 내 보고서 경로여야 합니다")
    return args


def main():
    args = parse_args()
    result = check_site(args)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print_summary(result)
    return int(result["status"] == "FAIL")


if __name__ == "__main__":
    raise SystemExit(main())
