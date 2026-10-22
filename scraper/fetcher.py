"""robots.txt を守り、間隔を空けて取得する。"""

from __future__ import annotations

import logging
import time
from typing import Callable
from urllib.parse import urljoin, urlsplit

import requests

from .robots import RobotsRules

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_BACKOFF = 120.0  # 待ちの上限（秒）。Retry-After が極端に長くても、これ以上は待たずに諦める


class DisallowedByRobots(Exception):
    """robots.txt で取得が許されていない URL。"""


class FetchError(Exception):
    """再試行しても取得できなかった。"""


class PoliteFetcher:
    """1つのサイトに負荷をかけないための取得役。

    - robots.txt を読み、許されていない URL は取得しない（Crawl-delay も守る）
    - 同じホストへのリクエストは ``min_interval`` 秒以上空ける
    - 429 / 5xx は待ち時間を倍にしながら ``max_retries`` 回まで再試行（Retry-After も守る。上限 MAX_BACKOFF 秒）
    - リダイレクト先が robots.txt で不可なら、その結果は使わない
    """

    def __init__(
        self,
        user_agent: str,
        min_interval: float = 1.0,
        max_retries: int = 3,
        timeout: float = 15.0,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if min_interval < 0:
            raise ValueError("min_interval は 0 以上")
        if max_retries < 0:
            raise ValueError("max_retries は 0 以上")
        self.user_agent = user_agent
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self._sleep = sleep
        self._clock = clock
        self._robots: dict[str, RobotsRules | None] = {}
        self._last_request: dict[str, float] = {}

    # --- robots.txt -------------------------------------------------------
    def _origin(self, url: str) -> str:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}"

    def _load_robots(self, origin: str) -> RobotsRules | None:
        """robots.txt を読む。戻り値 None は「制限なし」。

        RFC 9309 に合わせ、4xx は制限なし、5xx・通信エラーは全て不可として扱う。
        """
        robots_url = urljoin(origin, "/robots.txt")
        try:
            res = self._request("GET", robots_url, check_robots=False, retry=False)
        except requests.RequestException as exc:
            log.warning("robots.txt を読めないため取得を止めます: %s (%s)", robots_url, exc)
            return RobotsRules.disallow_all()
        if 400 <= res.status_code < 500:
            return None
        if res.status_code >= 500:
            log.warning("robots.txt が %s のため取得を止めます", res.status_code)
            return RobotsRules.disallow_all()
        return RobotsRules.parse(res.text)

    def _robots_for(self, url: str) -> RobotsRules | None:
        origin = self._origin(url)
        if origin not in self._robots:
            self._robots[origin] = self._load_robots(origin)
        return self._robots[origin]

    def allowed(self, url: str) -> bool:
        robots = self._robots_for(url)
        return True if robots is None else robots.can_fetch(self.user_agent, url)

    def _interval_for(self, url: str) -> float:
        robots = self._robots.get(self._origin(url))
        delay = robots.crawl_delay(self.user_agent) if robots else None
        if delay and delay > MAX_BACKOFF:
            log.warning("Crawl-delay %.0f 秒は長すぎるため %.0f 秒で扱います（件数を減らすか、相手に確認してください）", delay, MAX_BACKOFF)
            delay = MAX_BACKOFF
        return max(self.min_interval, float(delay or 0))

    # --- 取得 -------------------------------------------------------------
    def _wait_turn(self, url: str) -> None:
        host = urlsplit(url).netloc
        last = self._last_request.get(host)
        if last is not None:
            wait = self._interval_for(url) - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_request[host] = self._clock()

    def _request(self, method: str, url: str, check_robots: bool = True, retry: bool = True) -> requests.Response:
        if check_robots and not self.allowed(url):
            raise DisallowedByRobots(url)
        attempts = self.max_retries + 1 if retry else 1
        backoff = max(self.min_interval, 1.0)
        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            self._wait_turn(url)
            try:
                res = self.session.request(method, url, timeout=self.timeout)
            except requests.RequestException as exc:
                last_exc = exc
                log.warning("通信エラー (%d/%d): %s %s", attempt, attempts, url, exc)
            else:
                redirected_to = getattr(res, "url", url) or url
                if check_robots and getattr(res, "history", None) and not self.allowed(redirected_to):
                    raise DisallowedByRobots(f"{url} → {redirected_to}")
                if res.status_code not in RETRY_STATUSES or not retry:
                    return res
                last_exc = FetchError(f"HTTP {res.status_code}: {url}")
                log.warning("HTTP %d (%d/%d): %s", res.status_code, attempt, attempts, url)
                retry_after = res.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    backoff = max(backoff, float(retry_after))
            if attempt < attempts:
                if backoff > MAX_BACKOFF:
                    log.warning("待ちが %.0f 秒を超えるため再試行をやめます: %s", MAX_BACKOFF, url)
                    break
                self._sleep(backoff)
                backoff *= 2
        if not retry and isinstance(last_exc, requests.RequestException):
            raise last_exc
        raise FetchError(f"再試行しても取得できませんでした: {url}") from last_exc

    def get_text(self, url: str) -> str:
        """HTML を文字列で返す。4xx は FetchError。"""
        res = self._request("GET", url)
        if res.status_code >= 400:
            raise FetchError(f"HTTP {res.status_code}: {url}")
        if not res.encoding or res.encoding.lower() == "iso-8859-1":
            res.encoding = res.apparent_encoding
        return res.text
