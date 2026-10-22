"""一覧ページから項目を取り出す。

見本は練習用サイト https://books.toscrape.com/ の一覧ページの形に合わせている。
別のサイトに使う時は、この ``SELECTORS`` と ``parse_item`` だけを書き換える。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

SELECTORS = {
    "item": "article.product_pod",
    "title": "h3 a",
    "price": ".price_color",
    "availability": ".availability",
    "rating": "p.star-rating",
    "next": "li.next a",
}

RATING_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


@dataclass
class Item:
    title: str
    price: float | None
    currency: str
    in_stock: bool
    rating: int | None
    url: str

    def to_dict(self) -> dict:
        return asdict(self)


FIELDNAMES = ["title", "price", "currency", "in_stock", "rating", "url"]


def parse_price(text: str) -> tuple[float | None, str]:
    """'£51.77' → (51.77, '£')。読めない時は (None, '')。"""
    text = (text or "").strip()
    match = re.search(r"([^\d\s.,-]*)\s*([\d,]+(?:\.\d+)?)", text)
    if not match:
        return None, ""
    return float(match.group(2).replace(",", "")), match.group(1)


def parse_item(node: Tag, base_url: str) -> Item:
    link = node.select_one(SELECTORS["title"])
    title = (link.get("title") or link.get_text(strip=True)) if link else ""
    href = urljoin(base_url, link["href"]) if link and link.has_attr("href") else ""
    price_node = node.select_one(SELECTORS["price"])
    price, currency = parse_price(price_node.get_text() if price_node else "")
    avail_node = node.select_one(SELECTORS["availability"])
    in_stock = bool(avail_node and "in stock" in avail_node.get_text(" ", strip=True).lower())
    rating_node = node.select_one(SELECTORS["rating"])
    rating = None
    if rating_node:
        for cls in rating_node.get("class", []):
            if cls in RATING_WORDS:
                rating = RATING_WORDS[cls]
    return Item(title=title, price=price, currency=currency, in_stock=in_stock, rating=rating, url=href)


def parse_list_page(html: str, base_url: str) -> tuple[list[Item], str | None]:
    """一覧ページ1枚 → (項目のリスト, 次のページの URL または None)。"""
    soup = BeautifulSoup(html, "html.parser")
    items = [parse_item(node, base_url) for node in soup.select(SELECTORS["item"])]
    next_link = soup.select_one(SELECTORS["next"])
    next_url = urljoin(base_url, next_link["href"]) if next_link and next_link.has_attr("href") else None
    return items, next_url
