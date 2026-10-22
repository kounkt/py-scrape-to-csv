from __future__ import annotations

from pathlib import Path

import pytest
import requests

FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "", headers: dict | None = None, url: str = "", history: list | None = None):
        self.status_code = status_code
        self.url = url
        self.history = history or []
        self.text = text
        self.headers = headers or {}
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"


class FakeSession:
    """URL ごとに決めた応答を返す。リスト値なら順に返す（再試行の確認用）。"""

    def __init__(self, routes: dict):
        self.routes = routes
        self.headers: dict = {}
        self.calls: list[str] = []

    def request(self, method, url, timeout=None):
        self.calls.append(url)
        route = self.routes.get(url)
        if route is None:
            return FakeResponse(404, "not found")
        if isinstance(route, list):
            route = route.pop(0) if len(route) > 1 else route[0]
        if isinstance(route, Exception):
            raise route
        return route


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.now += seconds


@pytest.fixture
def fixture_html():
    return lambda name: (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def fake_clock():
    return FakeClock()


__all__ = ["FakeResponse", "FakeSession", "FakeClock", "requests"]
