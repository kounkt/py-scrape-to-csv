"""robots.txt の読み取り（RFC 9309 に沿った最小の実装）。

標準ライブラリの urllib.robotparser は ``*`` と ``$`` を解釈しないため、自前で判定する。
- User-agent は大文字小文字を区別せずに一致を見る。合う組が無ければ ``*`` の組を使う
- Allow / Disallow は「最も長く一致した規則」が勝つ。同じ長さなら Allow が勝つ
- ``*`` は任意の文字列、末尾の ``$`` はパスの終わりを表す
- Crawl-delay は RFC の外だが、広く使われているので読む
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass
class _Group:
    agents: list[str] = field(default_factory=list)
    rules: list[tuple[bool, str]] = field(default_factory=list)  # (allow, pattern)
    crawl_delay: float | None = None


def _product_token(user_agent: str) -> str:
    """'my-bot/1.0 (+https://...)' → 'my-bot'"""
    return re.split(r"[/\s]", user_agent.strip(), maxsplit=1)[0].lower()


def _pattern_to_regex(pattern: str) -> re.Pattern:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = ".*".join(re.escape(part) for part in body.split("*"))
    return re.compile(regex + ("$" if anchored else ""))


class RobotsRules:
    def __init__(self, groups: list[_Group]):
        self._groups = groups

    @classmethod
    def parse(cls, text: str) -> "RobotsRules":
        groups: list[_Group] = []
        current: _Group | None = None
        last_was_agent = False
        text = text.lstrip("\ufeff")  # 先頭の BOM で1行目の User-agent が読めなくなるのを防ぐ
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (part.strip() for part in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if current is None or not last_was_agent:
                    current = _Group()
                    groups.append(current)
                current.agents.append(value.lower())
                last_was_agent = True
                continue
            last_was_agent = False
            if current is None:
                continue
            if key in ("allow", "disallow") and value:
                current.rules.append((key == "allow", value))
            elif key == "crawl-delay":
                try:
                    current.crawl_delay = float(value)
                except ValueError:
                    pass
        return cls(groups)

    @classmethod
    def disallow_all(cls) -> "RobotsRules":
        return cls.parse("User-agent: *\nDisallow: /\n")

    def _groups_for(self, user_agent: str) -> list[_Group]:
        token = _product_token(user_agent)
        matched = [g for g in self._groups if token in g.agents]
        return matched or [g for g in self._groups if "*" in g.agents]

    def can_fetch(self, user_agent: str, url: str) -> bool:
        parts = urlsplit(url)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        if parts.path == "/robots.txt":
            return True
        best_len = -1
        allowed = True
        for group in self._groups_for(user_agent):
            for allow, pattern in group.rules:
                if _pattern_to_regex(pattern).match(path):
                    length = len(pattern)
                    if length > best_len or (length == best_len and allow):
                        best_len, allowed = length, allow
        return allowed

    def crawl_delay(self, user_agent: str) -> float | None:
        delays = [g.crawl_delay for g in self._groups_for(user_agent) if g.crawl_delay is not None]
        return max(delays) if delays else None
