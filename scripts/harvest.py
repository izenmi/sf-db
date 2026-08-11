#!/usr/bin/env python3
"""楽天ブックスのSFジャンルを人気順に舐めて、works.json に未登録の候補をTSVで列挙する。

  RAKUTEN_APP_ID=... RAKUTEN_ACCESS_KEY=... \
    python3 scripts/harvest.py --from-page 1 --pages 4 > cand.tsv

suggest_candidates.py(mystery-db から継承)との違いは3つ:

1. **ジャンルが SF・ホラー(001004002)** … 楽天ブックスの「小説・エッセイ」直下でSFを含む
   リーフジャンルはここだけ。**ホラーが同居しているので選別は必ず目視で行う**
2. **出力がTSV1行1件** … JSONを読むとトークンを食うので、判断に要る項目だけを1行に畳む。
   `titleKana` と `itemCaption` まで持ってくるので、採用と決めた候補について
   「読みを引き直す」「紹介文を取りに行く」ための往復が要らない
3. **除外リストを外から渡せる**(`--skip`) … 一度見て見送った候補が次のページ送りで
   また出てくるのを防ぐ。works.json との突合(正規化タイトル)は従来どおり自動

**あらすじの下敷きに caption を使ってよいが、転記は禁止**(CLAUDE.md のデータ入力ルール)。
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "public" / "data" / "source"
API = "https://openapi.rakuten.co.jp/services/api/BooksBook/Search/20170404"
REFERER = "https://izenmi.github.io/sf-db/"
SF_GENRE = "001004002"  # 小説・エッセイ > SF・ホラー(リーフ)

# 小説そのものでない商品。ジャンル指定だけでは混ざってくるので機械的に落とす。
REJECT = re.compile(
    r"攻略|図鑑|ムック|写真集|カレンダー|ガイドブック|設定資料|画集|ぬりえ|"
    r"CD|DVD|Blu-ray|フィギュア|ポスター|複製|グッズ|"
    r"コミック|漫画|まんが|コミックス|アンソロジーコミック"
)
VOLUME_TAIL = re.compile(r"[（(]?[上中下][)）]?$|[上中下]巻$")


def norm(x: str) -> str:
    x = re.sub(r"[【〔［\[].*?[】〕］\]]", "", x or "")
    return re.sub(r"[\s　・:：!！?？〜~\-—–ー、。,.（）()『』「」/]", "", x).lower()


def fetch(params, app, key):
    p = {"applicationId": app, "accessKey": key, "format": "json", "hits": "30"}
    p.update(params)
    req = urllib.request.Request(
        API + "?" + urllib.parse.urlencode(p),
        headers={"Referer": REFERER, "Origin": "https://izenmi.github.io"},
    )
    for attempt in range(4):
        try:
            return json.load(urllib.request.urlopen(req, timeout=45))
        except Exception:
            time.sleep(3 * (attempt + 1))
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-page", type=int, default=1)
    ap.add_argument("--pages", type=int, default=4)
    ap.add_argument("--sort", default="sales")
    ap.add_argument("--title", help="タイトルに含む語で絞る(省略時はジャンル全体)")
    ap.add_argument("--genre", default=SF_GENRE)
    ap.add_argument("--skip", help="見送った候補のタイトルを1行1件で並べたファイル")
    ap.add_argument("--caption", type=int, default=200, help="紹介文の切り詰め文字数")
    args = ap.parse_args()

    app, key = os.environ.get("RAKUTEN_APP_ID"), os.environ.get("RAKUTEN_ACCESS_KEY")
    if not app or not key:
        sys.exit("RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY が必要です。")

    have = {norm(w["title"]) for w in json.load(open(SRC / "works.json"))}
    if args.skip and Path(args.skip).exists():
        have |= {norm(line) for line in Path(args.skip).read_text(encoding="utf-8").splitlines() if line.strip()}

    seen, rows = set(), []
    for page in range(args.from_page, args.from_page + args.pages):
        spec = {"booksGenreId": args.genre, "sort": args.sort, "page": str(page)}
        if args.title:
            spec["title"] = args.title
        items = fetch(spec, app, key).get("Items", [])
        if not items:
            break
        for it in items:
            i = it["Item"]
            title = re.sub(r"[【〔［\[].*?[】〕］\]]", "", i["title"]).strip()
            if REJECT.search(title):
                continue
            base = VOLUME_TAIL.sub("", title).strip()
            k = norm(base)
            if not k or k in have or k in seen:
                continue
            seen.add(k)
            caption = re.sub(r"\s+", " ", i.get("itemCaption") or "")[: args.caption]
            rows.append("\t".join([
                base,
                re.sub(r"[（(].*?[)）]", "", i.get("titleKana") or "").strip(),
                (i.get("author") or "").replace("\t", " "),
                i.get("publisherName") or "",
                (i.get("salesDate") or "")[:4],
                i.get("isbn") or "",
                caption,
            ]))
        time.sleep(1.2)

    print(f"# page {args.from_page}-{args.from_page + args.pages - 1} / 未登録 {len(rows)}件")
    print("# title\tkana\tauthor\tpublisher\tsalesYear\tisbn\tcaption")
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
