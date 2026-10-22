"""コマンドラインの入口。

例:
    python -m scraper.cli --start-url https://books.toscrape.com/ --max-pages 2 --out output/books.csv
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from urllib.parse import urlsplit

from .exporter import write_csv, write_xlsx
from .fetcher import DisallowedByRobots, FetchError, PoliteFetcher
from .parser import FIELDNAMES, parse_list_page

DEFAULT_UA = "py-scrape-to-csv/1.0 (+https://github.com/kounkt/py-scrape-to-csv)"

log = logging.getLogger("scraper")


def crawl(fetcher: PoliteFetcher, start_url: str, max_pages: int) -> list[dict]:
    """一覧ページを「次へ」でたどり、項目を集める。同じ URL は2回取らず、別のホストへは移らない。"""
    rows: list[dict] = []
    seen: set[str] = set()
    host = urlsplit(start_url).netloc
    url: str | None = start_url
    pages = 0
    while url and pages < max_pages and url not in seen:
        seen.add(url)
        html = fetcher.get_text(url)
        items, url = parse_list_page(html, url)
        if url and urlsplit(url).netloc != host:
            log.warning("次のページが別のホストのため止めます: %s", url)
            url = None
        rows.extend(item.to_dict() for item in items)
        pages += 1
        log.info("%d ページ目：%d 件（累計 %d 件）", pages, len(items), len(rows))
    return rows


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="一覧ページを順にたどって CSV / Excel に書き出す")
    p.add_argument("--start-url", required=True, help="最初の一覧ページの URL")
    p.add_argument("--max-pages", type=int, default=1, help="たどるページ数の上限（既定 1）")
    p.add_argument("--out", default="output/result.csv", help="出力先（拡張子 .csv / .xlsx で形式が決まる）")
    p.add_argument("--delay", type=float, default=1.0, help="同じサイトへのリクエストの最小間隔（秒・既定 1.0）")
    p.add_argument("--user-agent", default=DEFAULT_UA, help="名乗る User-Agent（連絡先を入れる）")
    p.add_argument("-v", "--verbose", action="store_true", help="詳しいログ")
    return p


def main(argv: list[str] | None = None, fetcher: PoliteFetcher | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    if args.max_pages < 1:
        log.error("--max-pages は 1 以上")
        return 2
    if args.delay < 0:
        log.error("--delay は 0 以上")
        return 2
    if urlsplit(args.start_url).scheme not in ("http", "https"):
        log.error("--start-url は http:// か https:// で始まる URL")
        return 2
    out = Path(args.out)
    if out.suffix.lower() not in (".csv", ".xlsx"):
        log.error("--out の拡張子は .csv か .xlsx")
        return 2
    fetcher = fetcher or PoliteFetcher(user_agent=args.user_agent, min_interval=args.delay)
    try:
        rows = crawl(fetcher, args.start_url, args.max_pages)
    except DisallowedByRobots as exc:
        log.error("robots.txt で許可されていない URL です: %s", exc)
        return 3
    except FetchError as exc:
        log.error("%s", exc)
        return 4
    if not rows:
        log.warning("取れた項目が 0 件でした。parser.py の SELECTORS が対象ページに合っているか確かめてください")
        return 5
    writer = write_xlsx if out.suffix.lower() == ".xlsx" else write_csv
    count = writer(rows, out, FIELDNAMES)
    log.info("%d 件を書き出しました: %s", count, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
