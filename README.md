# py-scrape-to-csv

Web の一覧ページを「次へ」でたどって項目を集め、**CSV または Excel** に書き出す Python の雛形です。
相手のサイトに迷惑をかけないための決まり（robots.txt・アクセス間隔・再試行の待ち）を最初から組み込んでいます。

見本の取得先は、スクレイピングの練習用に公開されているサイト [books.toscrape.com](https://books.toscrape.com/) です。

## 目的

- 手作業でコピーしている一覧（商品・求人・店舗・記事など）を、決まった形の表に落とす
- 定期的に同じページを取りに行き、差分を見られるようにする土台にする
- 取得先のサイトを変える時に、直す場所を1か所（`scraper/parser.py`）に絞る

## 守っていること

| 決まり | 中身 |
| --- | --- |
| robots.txt | 取得前に読み、許可されていない URL は取りに行かない。`*` と `$` を含む規則も RFC 9309 に沿って判定する（標準ライブラリの robotparser はこれを解釈しないため自前で実装）。`Crawl-delay` があればそれに合わせる（120 秒が上限）。robots.txt が 5xx・通信エラーの時は安全側に倒して全て止める。リダイレクト先が不可の時はその結果を使わない |
| アクセス間隔 | 同じホストへは `--delay` 秒（既定 1 秒）以上空ける |
| 再試行 | 429・5xx は 1→2→4 秒と待ちを倍にして最大3回。`Retry-After` があれば従う（待ちが 120 秒を超える時は諦めて止める）。404 などは再試行しない |
| 範囲 | 「次へ」が別のホストを指したら、そこで止める |
| 名乗り | User-Agent に名前と連絡先を入れる（`--user-agent`） |
| Excel の安全 | CSV は `=` `+` `-` `@` で始まる文字列の先頭に `'` を付ける。`.xlsx` はセルの型を文字列に固定する。どちらも開いた時に数式として動かない |

取得してよいかは robots.txt だけでは決まりません。**対象サイトの利用規約**で自動取得が禁じられていないか、ログインが要るページでないか、取得したデータの使い道が著作権・個人情報の扱いに合っているかを、導入前に確かめてください。

## 中身

```
scraper/
  fetcher.py   取得役（robots.txt・間隔・再試行）
  robots.py    robots.txt の判定（* と $ に対応）
  parser.py    一覧ページの読み取り（サイトごとに書き換える所）
  exporter.py  CSV（UTF-8 BOM 付き）／Excel の書き出し
  cli.py       コマンドの入口
tests/         pytest（ネットにつながずに動く）
```

## 導入

Python 3.10 以上。

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows は .venv\Scripts\activate
pip install -r requirements-dev.txt
```

## 使い方

```bash
# 見本：練習用サイトの一覧を2ページ分、CSV に
python -m scraper.cli --start-url https://books.toscrape.com/ --max-pages 2 --out output/books.csv

# Excel で出す（拡張子で決まる）
python -m scraper.cli --start-url https://books.toscrape.com/ --max-pages 2 --out output/books.xlsx
```

| オプション | 既定 | 中身 |
| --- | --- | --- |
| `--start-url` | （必須） | 最初の一覧ページ |
| `--max-pages` | 1 | たどるページ数の上限 |
| `--out` | `output/result.csv` | 出力先。`.csv` か `.xlsx` |
| `--delay` | 1.0 | 同じサイトへの最小間隔（秒） |
| `--user-agent` | `py-scrape-to-csv/1.0 (+リポジトリの URL)` | 名乗り。本番では依頼主の連絡先に変える |
| `-v` | | 詳しいログ |

終了コード：`0` 成功／`2` 引数の誤り／`3` robots.txt で不可／`4` 取得に失敗／`5` 取れた項目が 0 件（セレクタの見直しの合図）

出力の列：`title, price, currency, in_stock, rating, url`

## 別のサイトに使う

1. `scraper/parser.py` の `SELECTORS` を、対象ページの CSS セレクタに書き換える
2. 取りたい項目が違う時は `Item` と `parse_item`、`FIELDNAMES` を合わせて直す
3. 対象ページを1枚保存して `tests/fixtures/` に置き、`tests/test_parser.py` に期待値を書く
4. `pytest` が通ってから、`--max-pages 1` で本物のサイトに1回だけ当てる

## 動作確認

```bash
pytest
```

`36 passed` と出れば成功です。テストは保存した HTML と偽の通信を使うので、ネットにつながずに動き、相手のサイトにもアクセスしません。

実際の取得は、上の「使い方」の見本を1回動かし、`output/books.csv` に 40 件（見出しを入れて 41 行）出ることを確かめます。

## よくある質問

**Q. Excel で開くと文字化けする**
A. CSV は BOM 付き UTF-8 で書いているので、通常はそのまま開けます。古い Excel で化ける時は `.xlsx` で出してください。

**Q. JavaScript で後から表示されるページは取れますか？**
A. この雛形は HTML をそのまま読むので取れません。その場合は Playwright などのブラウザ操作に差し替えます（取得役 `fetcher.py` だけを入れ替える形）。

**Q. もっと速く取りたい**
A. 間隔を詰めると相手のサーバーに負荷がかかり、遮断や規約違反の原因になります。件数が多い時は、夜間に時間をかけて回す、相手が API や CSV の配布を用意していないか先に探す、を勧めています。

**Q. 毎日自動で動かしたい**
A. cron（Mac/Linux）やタスク スケジューラ（Windows）、GitHub Actions の定期実行で `python -m scraper.cli ...` を呼びます。

## 費用の目安

**運用費**
- 手元の PC で動かすなら 0 円。常時動かすなら小さなサーバー（月 数百円〜）か GitHub Actions の無料枠

**導入の作業費（参考）**
ログイン不要・一覧1種類・項目 5〜10 個のサイト1つ分は、作業 4〜6 時間ほどが目安です。ログインが要る、JavaScript で描画される、ページの形が複数ある、といった場合は要件を伺ってから見積もります。

取得先の利用規約の確認と、取得したデータの使い道の判断は、お客様にお願いしています。

## ライセンス

MIT License — © 2026 CHIERO Inc.
