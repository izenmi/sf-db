#!/usr/bin/env python3
"""1作品のNDL書誌を「年|出版社|書名」で古い順に並べる。初出年の食い違いを潰すための道具。

  python3 scripts/editions.py "継ぐのは誰か" 小松左京

lookup.py の `ndlFirst` は同名書誌の最古年をそのまま返すので、雑誌掲載・全集・
同名異作を巻き込んで実際の単行本初刊より古い年を出すことがある。**受賞年と
2年以上ずれた候補だけ**この道具で版を並べて、単行本の初刊を目で選ぶ。
"""
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

NS = {"dc": "http://purl.org/dc/elements/1.1/"}
DROP = re.compile(r"[\s　・:：!！?？〜~\-—–ー、。,.（）()『』「」/【】\[\]]")


def norm(s):
    return DROP.sub("", unicodedata.normalize("NFKC", s or "")).lower()


def main():
    title = sys.argv[1]
    author = sys.argv[2] if len(sys.argv) > 2 else ""
    p = {"title": title, "cnt": "50"}
    if author:
        p["creator"] = author
    url = "https://ndlsearch.ndl.go.jp/api/opensearch?" + urllib.parse.urlencode(p)
    raw = urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "sf-db-probe/1.0"}), timeout=45
    ).read()
    rows = []
    for item in ET.fromstring(raw).iter("item"):
        t = item.findtext("title") or ""
        d = item.findtext("dc:date", namespaces=NS) or item.findtext("pubDate") or ""
        pub = item.findtext("dc:publisher", namespaces=NS) or ""
        m = re.search(r"(1[5-9]\d\d|20\d\d)", d)
        rows.append((int(m.group(1)) if m else 9999, pub, t))
    rows.sort()
    for y, pub, t in rows[:25]:
        print(f"{y if y != 9999 else '????'}\t{pub}\t{t[:48]}")


if __name__ == "__main__":
    main()
