import pytest
import requests

from scraper.fetcher import DisallowedByRobots, FetchError, PoliteFetcher
from tests.conftest import FakeResponse, FakeSession

SITE = "https://site.example.test"
ROBOTS = SITE + "/robots.txt"


def make(routes, clock, **kw):
    session = FakeSession(routes)
    fetcher = PoliteFetcher("test-bot/1.0", session=session, sleep=clock.sleep, clock=clock.clock, **kw)
    return fetcher, session


def test_robots_disallow_blocks_request(fake_clock):
    robots = "User-agent: *\nDisallow: /private/\n"
    fetcher, session = make({ROBOTS: FakeResponse(200, robots), SITE + "/private/a": FakeResponse(200, "secret")}, fake_clock)
    assert fetcher.allowed(SITE + "/public/") is True
    with pytest.raises(DisallowedByRobots):
        fetcher.get_text(SITE + "/private/a")
    assert SITE + "/private/a" not in session.calls  # 取りに行っていない


def test_robots_404_means_allow_all(fake_clock):
    fetcher, _ = make({SITE + "/page": FakeResponse(200, "ok")}, fake_clock)
    assert fetcher.get_text(SITE + "/page") == "ok"


def test_robots_5xx_means_disallow_all(fake_clock):
    fetcher, _ = make({ROBOTS: FakeResponse(503, ""), SITE + "/page": FakeResponse(200, "ok")}, fake_clock)
    assert fetcher.allowed(SITE + "/page") is False


def test_robots_network_error_means_disallow_all(fake_clock):
    fetcher, _ = make({ROBOTS: requests.ConnectionError("down")}, fake_clock)
    assert fetcher.allowed(SITE + "/page") is False


def test_min_interval_between_requests(fake_clock):
    routes = {SITE + "/a": FakeResponse(200, "a"), SITE + "/b": FakeResponse(200, "b")}
    fetcher, _ = make(routes, fake_clock, min_interval=2.0)
    fetcher.get_text(SITE + "/a")
    fetcher.get_text(SITE + "/b")
    # robots.txt → /a → /b の3回。2回目・3回目の前に 2 秒ずつ待つ
    assert fake_clock.sleeps == [2.0, 2.0]


def test_crawl_delay_from_robots_is_respected(fake_clock):
    robots = "User-agent: *\nCrawl-delay: 5\n"
    routes = {ROBOTS: FakeResponse(200, robots), SITE + "/a": FakeResponse(200, "a"), SITE + "/b": FakeResponse(200, "b")}
    fetcher, _ = make(routes, fake_clock, min_interval=1.0)
    fetcher.get_text(SITE + "/a")
    fetcher.get_text(SITE + "/b")
    assert fake_clock.sleeps[-1] == 5.0


def test_retry_on_503_then_success(fake_clock):
    routes = {SITE + "/a": [FakeResponse(503), FakeResponse(503), FakeResponse(200, "ok")]}
    fetcher, session = make(routes, fake_clock, min_interval=0, max_retries=3)
    assert fetcher.get_text(SITE + "/a") == "ok"
    assert session.calls.count(SITE + "/a") == 3
    assert fake_clock.sleeps == [1.0, 2.0]  # 待ちは倍に増える


def test_retry_after_header(fake_clock):
    routes = {SITE + "/a": [FakeResponse(429, headers={"Retry-After": "7"}), FakeResponse(200, "ok")]}
    fetcher, _ = make(routes, fake_clock, min_interval=0)
    assert fetcher.get_text(SITE + "/a") == "ok"
    assert fake_clock.sleeps == [7.0]


def test_gives_up_after_max_retries(fake_clock):
    routes = {SITE + "/a": [FakeResponse(500)]}
    fetcher, session = make(routes, fake_clock, min_interval=0, max_retries=2)
    with pytest.raises(FetchError):
        fetcher.get_text(SITE + "/a")
    assert session.calls.count(SITE + "/a") == 3


def test_404_is_not_retried(fake_clock):
    fetcher, session = make({}, fake_clock, min_interval=0)
    with pytest.raises(FetchError):
        fetcher.get_text(SITE + "/missing")
    assert session.calls.count(SITE + "/missing") == 1


def test_user_agent_is_set(fake_clock):
    fetcher, session = make({}, fake_clock)
    assert session.headers["User-Agent"] == "test-bot/1.0"


def test_negative_interval_rejected():
    with pytest.raises(ValueError):
        PoliteFetcher("x", min_interval=-1)


def test_retry_after_too_long_gives_up(fake_clock):
    routes = {SITE + "/a": [FakeResponse(503, headers={"Retry-After": "86400"}), FakeResponse(200, "ok")]}
    fetcher, _ = make(routes, fake_clock, min_interval=0)
    with pytest.raises(FetchError):
        fetcher.get_text(SITE + "/a")
    assert fake_clock.sleeps == []  # 1日待つことはしない


def test_redirect_to_disallowed_path_is_rejected(fake_clock):
    robots = "User-agent: *\nDisallow: /private/\n"
    redirected = FakeResponse(200, "secret", url=SITE + "/private/x", history=[FakeResponse(302)])
    fetcher, _ = make({ROBOTS: FakeResponse(200, robots), SITE + "/go": redirected}, fake_clock)
    with pytest.raises(DisallowedByRobots):
        fetcher.get_text(SITE + "/go")


def test_wildcard_rules_are_respected(fake_clock):
    robots = "User-agent: *\nDisallow: /*?sort=\nDisallow: /*.pdf$\n"
    fetcher, _ = make({ROBOTS: FakeResponse(200, robots)}, fake_clock)
    assert fetcher.allowed(SITE + "/list?sort=price") is False
    assert fetcher.allowed(SITE + "/docs/a.pdf") is False
    assert fetcher.allowed(SITE + "/docs/a.pdf?x=1") is True
    assert fetcher.allowed(SITE + "/list") is True


def test_crawl_delay_is_capped(fake_clock):
    robots = "User-agent: *\nCrawl-delay: 86400\n"
    routes = {ROBOTS: FakeResponse(200, robots), SITE + "/a": FakeResponse(200, "a"), SITE + "/b": FakeResponse(200, "b")}
    fetcher, _ = make(routes, fake_clock)
    fetcher.get_text(SITE + "/a")
    fetcher.get_text(SITE + "/b")
    assert fake_clock.sleeps[-1] == 120.0
