#!/usr/bin/env python3
"""covers-cache.json の1件を手で差し替える。自動取得が外したときの手当て用。

  # 候補を見る
  RAKUTEN_APP_ID=... RAKUTEN_ACCESS_KEY=... python3 scripts/setcover.py --search "豹頭の仮面"
  # 採用して書き込む
  ... python3 scripts/setcover.py guin-saga --isbn 9784150304829 --note "第1巻の書影を採用"
  # プレースホルダーに戻す
  ... python3 scripts/setcover.py guin-saga --drop --note "適切な書影が見つからない"

**なぜ手当てが要るか**: fetch-covers.mjs はタイトル前方一致+著者一致で選ぶため、
(1) ハンドブック・ガイドブックなどの関連書、(2) 上下巻の下巻、を拾うことがある。
実例として『グイン・サーガ』が『グイン・サーガ・ハンドブック』を、
『零號琴』『彗星狩り』『消滅の光輪』が下巻の書影を拾った。**必ず実画像まで開いて確認すること。**
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / "public" / "data" / "source" / "covers-cache.json"
API = "https://openapi.rakuten.co.jp/services/api/BooksBook/Search/20170404"
KOBO = "https://openapi.rakuten.co.jp/services/api/Kobo/EbookSearch/20170426"
HDR = {"Referer": "https://izenmi.github.io/sf-db/", "Origin": "https://izenmi.github.io"}


def call(params, endpoint=None):
    p = {"applicationId": os.environ["RAKUTEN_APP_ID"], "accessKey": os.environ["RAKUTEN_ACCESS_KEY"],
         "format": "json", "hits": "20"}
    p.update(params)
    req = urllib.request.Request((endpoint or API) + "?" + urllib.parse.urlencode(p), headers=HDR)
    items = json.load(urllib.request.urlopen(req, timeout=45)).get("Items", [])
    return [i.get("Item", i) for i in items]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_id", nargs="?")
    ap.add_argument("--search")
    ap.add_argument("--isbn")
    ap.add_argument("--drop", action="store_true")
    ap.add_argument("--kobo", action="store_true", help="紙が絶版の作品向け。楽天Koboの電子版から書影を採る")
    ap.add_argument("--pick", type=int, default=0, help="--kobo の候補番号")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    if args.search:
        src = call({"title": args.search}, KOBO if args.kobo else None)
        for n, i in enumerate(src):
            print(f"{n}\t{i.get('isbn','') or i.get('itemNumber','')}\t{i.get('title','')[:44]}"
                  f"\t{i.get('author','')[:18]}\t{i.get('publisherName','')}")
        return

    if not args.work_id:
        sys.exit("work_id が必要です。")
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    entry = cache.get(args.work_id, {})

    if args.drop:
        cache[args.work_id] = {"title": entry.get("title", ""), "isbn": None, "coverUrl": None,
                               "matchedTitle": None, "source": None, "note": args.note}
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{args.work_id}: プレースホルダーに戻した")
        return

    if args.kobo:
        items = call({"title": args.isbn}, KOBO)
        if not items:
            sys.exit(f"Koboに {args.isbn} が見つからない")
        i = items[args.pick]
    else:
        items = call({"isbn": args.isbn})
        if not items:
            sys.exit(f"ISBN {args.isbn} の商品が見つからない")
        i = items[0]
    url = i.get("largeImageUrl") or i.get("mediumImageUrl")
    cache[args.work_id] = {
        "title": entry.get("title", i.get("title", "")),
        "isbn": i.get("isbn"),
        "matchedTitle": i.get("title"),
        "coverUrl": url.replace("?_ex=200x200", "?_ex=400x400") if url else None,
        "rakutenItemUrl": i.get("itemUrl"),
        "source": "rakuten-kobo" if args.kobo else "rakuten-books",
        "note": args.note,
    }
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{args.work_id}: {i.get('title')} ({i.get('isbn')})")


if __name__ == "__main__":
    main()
