#!/usr/bin/env python3
"""Wikipediaの「あらすじ」「概要」節だけを抜き出す。紹介文が手に入らない作品の最後の砦。

  python3 scripts/plot.py titles.txt [--chars 420]

titles.txt は1行1件。`表示名|記事名` と書けば記事名のほうで引く(同名記事の曖昧さ回避用)。

**位置づけ**: あらすじの下敷きは (1) 楽天ブックスの出版社紹介文 → (2) 楽天Koboの紹介文
(ここまでは `scripts/lookup.py` が自動で拾う) → (3) この節、の順に当たる。絶版で
電子版もない古い作品はWikipediaしか残らない。**いずれの場合も転記は禁止**で、
150〜250字の独自要約に書き直すこと。

節が見つからない作品は `NONE` を返す。そこまでして情報が無い候補は
「実在確認できない候補は無理に埋めない」の原則どおり見送る(あらすじを想像で書かない)。
"""
import argparse
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

WANT = re.compile(r"^(あらすじ|概要|ストーリー|物語|内容|作品内容|プロット)$")


def fetch(title):
    url = ("https://ja.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext"
           "&format=json&redirects=1&titles=" + urllib.parse.quote(title))
    d = json.load(urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "sf-db-probe/1.0"}), timeout=45))
    for p in d.get("query", {}).get("pages", {}).values():
        return p.get("extract") or ""
    return ""


def section(text):
    """== 見出し == で切って、あらすじ相当の節の本文を返す。無ければ導入部。"""
    parts = re.split(r"\n==+\s*(.+?)\s*==+\n", "\n" + text)
    intro = parts[0]
    for i in range(1, len(parts) - 1, 2):
        if WANT.match(parts[i].strip()):
            body = parts[i + 1].strip()
            if body:
                return body
    return intro.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("titles")
    ap.add_argument("--chars", type=int, default=420)
    args = ap.parse_args()

    rows = [l.strip() for l in Path(args.titles).read_text(encoding="utf-8").splitlines()]
    for n, row in enumerate([r for r in rows if r and not r.startswith("#")], 1):
        label, _, page = row.partition("|")
        label, page = label.strip(), (page.strip() or row.strip())
        text = fetch(page)
        body = re.sub(r"\s+", " ", section(text)) if text else ""
        print(f"{n}\t{label}\t{body[:args.chars] if body else 'NONE'}")


if __name__ == "__main__":
    main()
