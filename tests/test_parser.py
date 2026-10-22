from scraper.parser import parse_list_page, parse_price

BASE = "https://books.example.test/"


def test_parse_list_page_items(fixture_html):
    items, next_url = parse_list_page(fixture_html("list_page1.html"), BASE)
    assert len(items) == 2
    first = items[0]
    assert first.title == "Sample Book One"  # 省略された表示名ではなく title 属性を使う
    assert first.price == 51.77
    assert first.currency == "£"
    assert first.in_stock is True
    assert first.rating == 3
    assert first.url == "https://books.example.test/catalogue/sample-book-one_1/index.html"
    assert items[1].in_stock is False
    assert items[1].price == 1234.5
    assert next_url == "https://books.example.test/catalogue/page-2.html"


def test_last_page_has_no_next(fixture_html):
    items, next_url = parse_list_page(fixture_html("list_page2.html"), BASE + "catalogue/page-2.html")
    assert [i.title for i in items] == ["Sample Book Three"]
    assert items[0].url == "https://books.example.test/catalogue/sample-book-three_3/index.html"
    assert next_url is None


def test_empty_page():
    assert parse_list_page("<html><body></body></html>", BASE) == ([], None)


def test_parse_price():
    assert parse_price("£51.77") == (51.77, "£")
    assert parse_price("¥1,200") == (1200.0, "¥")
    assert parse_price("") == (None, "")
    assert parse_price("price on request") == (None, "")
