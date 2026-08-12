#!/usr/bin/env python3
"""登録済み著者の未登録作品を楽天ブックスから列挙する。

楽天のSFジャンル(001004002)は在庫が200件足らずで候補源にならないが、
author= での著者引きは正確に効き、ISBN・版元・刊行年・紹介文が一度に揃う。
Wikipediaに記事のない作品まで拾えるので、wikicat.py と相補的に使う。

    RAKUTEN_APP_ID=... RAKUTEN_ACCESS_KEY=... python3 scripts/byauthor.py [著者id...]

引数を省略すると works.json に2作以上ある著者を刊行数の多い順に全員たどる。
出力はTSV(状態/著者/ISBN/タイトル/著者表記/版元/刊行日/紹介文の長さ)。
状態が st=NEW の行だけが候補。
"""
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
HDR = {
    "Referer": "https://izenmi.github.io/sf-db/",
    "Origin": "https://izenmi.github.io",
    "User-Agent": "sf-db/1.0",
}

# 小説でないもの・別メディア。harvest.py の REJECT より広めに取る。
REJECT = re.compile(
    r"攻略|図鑑|ムック|写真集|カレンダー|ガイドブック|設定資料|画集|ぬりえ|CD|DVD|Blu-ray"
    r"|フィギュア|ポスター|複製|グッズ|コミック|漫画|まんが|コミックス|絵本|脚本|シナリオ"
    r"|全集|事典|辞典|入門|読本|研究|論|評伝|自伝|対談|エッセイ|随筆|紀行|オーディオ"
)
# 巻次つきは第1巻だけ残す(下巻だけ候補に出ても意味がない)
VOLUME_TAIL = re.compile(r"[（(]?[上中下][)）]?\s*$|[上中下]巻\s*$|[（(]\s*\d+\s*[)）]\s*$|\s\d+\s*$")


def norm(s: str) -> str:
    s = re.sub(r"[\s　]+", "", s or "")
    s = re.sub(r"[〔［\[（(【].*?[】）)\]］〕]", "", s)
    s = s.replace("・", "").replace("＝", "").replace("=", "").replace("-", "").replace("ー", "")
    return s.lower()


def load():
    works = json.loads((SRC / "works.json").read_text(encoding="utf-8"))
    authors = json.loads((SRC / "authors.json").read_text(encoding="utf-8"))
    return works, authors


def fetch(author, page=1):
    p = {
        "applicationId": os.environ["RAKUTEN_APP_ID"],
        "accessKey": os.environ["RAKUTEN_ACCESS_KEY"],
        "format": "json",
        "hits": "30",
        "sort": "sales",
        "author": author,
        "page": str(page),
    }
    url = API + "?" + urllib.parse.urlencode(p)
    last = None
    for _ in range(4):
        try:
            req = urllib.request.Request(url, headers=HDR)
            return json.load(urllib.request.urlopen(req, timeout=45))
        except Exception as exc:  # 429/5xx は間を空けて引き直す
            last = exc
            time.sleep(8)
    print(f"# ERR {author}: {last}", file=sys.stderr)
    return {}


def main():
    works, authors = load()
    by_id = {a["id"]: a for a in authors}
    have = {norm(w["title"]) for w in works}
    for w in works:
        for alt in (w.get("originalTitle"), *(w.get("altTitles") or [])):
            if alt:
                have.add(norm(alt))

    if len(sys.argv) > 1:
        targets = [i for i in sys.argv[1:] if i in by_id]
    else:
        count = {}
        for w in works:
            for aid in w.get("authorIds", []):
                count[aid] = count.get(aid, 0) + 1
        targets = [i for i, _ in sorted(count.items(), key=lambda kv: -kv[1]) if i in by_id]

    print("st\t著者\tISBN\tタイトル\t著者表記\t版元\t刊行日\tcap")
    new = dup = 0
    for aid in targets:
        name = by_id[aid]["name"]
        data = fetch(name)
        for entry in data.get("Items", []):
            item = entry["Item"]
            title = item.get("title", "")
            if REJECT.search(title) or not item.get("isbn"):
                continue
            if VOLUME_TAIL.search(title) and not re.search(r"[（(]?[上1１]", title):
                continue
            key = norm(VOLUME_TAIL.sub("", title))
            if key in have:
                dup += 1
                st = "DUP"
            else:
                new += 1
                st = "NEW"
                have.add(key)
            if st == "DUP":
                continue
            print(
                "\t".join(
                    [
                        st,
                        name,
                        item["isbn"],
                        title,
                        item.get("author", ""),
                        item.get("publisherName", ""),
                        item.get("salesDate", ""),
                        str(len(item.get("itemCaption", ""))),
                    ]
                )
            )
        sys.stdout.flush()
        time.sleep(1)
    print(f"# NEW {new} / DUP {dup} / 著者 {len(targets)}", file=sys.stderr)


if __name__ == "__main__":
    main()
