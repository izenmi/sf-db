#!/usr/bin/env python3
"""Wikipediaの導入部から発表年の根拠を1行で抜き出す。NDLの初出年の裏取りに使う。

  python3 scripts/origyear.py titles.txt              # 日本語版(国内作品の発表年)
  python3 scripts/origyear.py titles.txt --lang en    # 英語版(海外作品の原著発表年)

titles.txt は1行1件。`表示名|検索語` と書くと検索語のほうでWikipediaを引く
(海外作品は邦題ではなく原題で引く必要があるため)。

**なぜ要るか**: NDLサーチの最古年は同名異作・全集・復刊を巻き込むので、
単独では firstPublishedYear の根拠にならない(mystery-db の CLAUDE.md に既知の落とし穴として
記録がある)。一方でWikipediaの導入部はたいてい「『X』は、YYYY年に刊行された」という
形をしているので、**年が入った最初の一文だけ**を出せば人が数秒で判断できる。

出力: `n | title | 年候補(カンマ区切り) | 根拠の一文(90字)`。
記事が無ければ `NOPAGE`。**年候補が複数出たら必ず根拠を読んで選ぶこと**(連載開始年と
単行本刊行年が併記されている場合がある)。
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

CHUNK = 20  # extracts API は exlimit=20 までまとめられる
YEAR = re.compile(r"(1[5-9]\d{2}|20\d{2})\s*年?")


def fetch_extracts(titles, lang):
    api = (f"https://{lang}.wikipedia.org/w/api.php?action=query&prop=extracts"
           "&exintro&explaintext&exlimit=20&format=json&redirects=1&titles=")
    req = urllib.request.Request(api + urllib.parse.quote("|".join(titles)),
                                 headers={"User-Agent": "sf-db-probe/1.0"})
    data = json.load(urllib.request.urlopen(req, timeout=45))
    q = data.get("query", {})
    # redirects/normalized を辿って「渡した名前 -> 実際のページ名」を作る
    alias = {}
    for key in ("normalized", "redirects"):
        for r in q.get(key, []):
            alias[r["from"]] = r["to"]
    pages = {p.get("title"): p.get("extract", "") for p in q.get("pages", {}).values()}

    def resolve(name):
        seen = set()
        while name in alias and name not in seen:
            seen.add(name)
            name = alias[name]
        return pages.get(name)

    return {t: resolve(t) for t in titles}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("titles")
    ap.add_argument("--lang", default="ja")
    ap.add_argument("--chars", type=int, default=90)
    args = ap.parse_args()

    rows = [l.strip() for l in Path(args.titles).read_text(encoding="utf-8").splitlines()]
    rows = [l for l in rows if l and not l.startswith("#")]
    labels = [r.partition("|")[0].strip() for r in rows]
    queries = [(r.partition("|")[2].strip() or r.partition("|")[0].strip()) for r in rows]

    extracts = {}
    for i in range(0, len(queries), CHUNK):
        extracts.update(fetch_extracts(queries[i:i + CHUNK], args.lang))

    for n, (label, query) in enumerate(zip(labels, queries), 1):
        text = extracts.get(query)
        if not text:
            print(f"{n}\t{label}\tNOPAGE")
            continue
        head = re.sub(r"\s+", " ", text)[:600]
        years = []
        for m in YEAR.finditer(head):
            y = m.group(1)
            if y not in years:
                years.append(y)
        # 年を含む最初の一文を根拠として出す
        sentence = ""
        for s in re.split(r"(?<=[。.])\s*", head):
            if YEAR.search(s):
                sentence = s[: args.chars]
                break
        print(f"{n}\t{label}\t{','.join(years[:5])}\t{sentence}")


if __name__ == "__main__":
    main()
