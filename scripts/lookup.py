#!/usr/bin/env python3
"""候補を「1行1件」に畳んで下調べする。楽天ブックス(書誌+紹介文)とNDLサーチ(初出年+原タイトル)を
1回のコマンドで突き合わせる、大量追加のときの主力ツール。

  RAKUTEN_APP_ID=... RAKUTEN_ACCESS_KEY=... \
    python3 scripts/lookup.py cand.txt [--sleep 2] [--caption 170]

cand.txt は1行1件、`タイトル|著者` 形式(著者は省略可、`#` 始まりと空行は無視)。

出力(タブ区切り):
  n  status  title  kana  author  publisher  ndlFirst  rakYear  isbn  originalTitle  caption

- **status=DUP なら works.json に既にある**。ネットワークアクセスもしないので、
  「詳しく調べる前に登録済みか確認する」というルールがこの1本で満たせる
- `ndlFirst` は NDL の同名書誌の最古年。**国内作品ならほぼ firstPublishedYear、
  海外作品なら邦訳初刊年(= jpPublishedYear)**になる。海外作品の原著発表年は
  ここには出ないので `scripts/origyear.py` で別に引くこと
- `caption` は楽天の出版社紹介文。**あらすじの下敷きにしてよいが転記は禁止**
- 楽天が拾えなくても NDL 側が取れていれば status=OK。両方外れたら MISS
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "public" / "data" / "source"
RAK = "https://openapi.rakuten.co.jp/services/api/BooksBook/Search/20170404"
KOBO = "https://openapi.rakuten.co.jp/services/api/Kobo/EbookSearch/20170426"
NDL = "https://ndlsearch.ndl.go.jp/api/opensearch"
REFERER = "https://izenmi.github.io/sf-db/"
NS = {"dc": "http://purl.org/dc/elements/1.1/", "dcndl": "http://ndl.go.jp/dcndl/terms/"}

DROP = re.compile(r"[\s　・:：!！?？〜~\-—–ー、。,.（）()『』「」/【】\[\]0-9０-９]")


def norm(s: str) -> str:
    return DROP.sub("", unicodedata.normalize("NFKC", s or "")).lower()


def get(url, headers=None, tries=4, sleep=2):
    for attempt in range(tries):
        try:
            return urllib.request.urlopen(
                urllib.request.Request(url, headers=headers or {}), timeout=45
            ).read()
        except Exception:
            time.sleep(sleep * (attempt + 1))
    return None


def rakuten(title, author, app, key):
    """楽天ブックスから書誌+紹介文。著者名が一致する候補を優先する。"""
    p = {"applicationId": app, "accessKey": key, "format": "json", "hits": "12",
         "title": re.sub(r"[?？!！・:：]", " ", title).strip()}
    raw = get(RAK + "?" + urllib.parse.urlencode(p),
              {"Referer": REFERER, "Origin": "https://izenmi.github.io"})
    if not raw:
        return None
    items = [i["Item"] for i in json.loads(raw).get("Items", [])]
    if not items:
        return None
    want_t, want_a = norm(title), norm(author)
    scored = []
    for i in items:
        t, a = norm(i.get("title", "")), norm(i.get("author", ""))
        if want_t not in t and t not in want_t:
            continue
        # 著者名を渡されたら一致を必須にする。同名異作(広瀬正『鏡の国のアリス』に対する
        # ルイス・キャロル、神林長平『プリズム』に対する百田尚樹)を実際に拾ったため。
        if want_a and want_a not in a:
            continue
        # 収録作の1つとして書名を含むだけの合集を弾く(『継ぐのは誰か?』で
        # 『日本SF傑作選2』の紹介文を拾った)。書名が問い合わせの2.5倍を超えたら別物とみなす。
        if len(t) > len(want_t) * 2.5 + 6:
            continue
        scored.append((len(t), i))  # 副題や版表記で伸びた書名より素の書名を上に置く
    if not scored:
        return None
    scored.sort(key=lambda x: x[0])
    return scored[0][1]


def kobo(title, author, app, key):
    """紹介文の予備。絶版で紙が流通していない古いSFでも電子版なら紹介文があることが多い。"""
    p = {"applicationId": app, "accessKey": key, "format": "json", "hits": "12", "title": title}
    raw = get(KOBO + "?" + urllib.parse.urlencode(p),
              {"Referer": REFERER, "Origin": "https://izenmi.github.io"})
    if not raw:
        return ""
    want_t, want_a = norm(title), norm(author)
    best = ""
    for it in json.loads(raw).get("Items", []):
        i = it.get("Item", it)
        t, a = norm(i.get("title", "")), norm(i.get("author", ""))
        if want_t not in t and t not in want_t:
            continue
        if want_a and want_a not in a:
            continue
        cap = (i.get("itemCaption") or "").strip()
        if cap and len(cap) > len(best):
            best = cap
    return best


def ndl(title, author, sleep):
    """絶版・品切れで楽天に無い作品でも、NDLなら読み・出版社・初出年が取れる。"""
    out = {"first": None, "firstPub": "", "orig": None, "kana": "", "publisher": "", "isbn": ""}
    p = {"title": title, "cnt": "20"}
    if author:
        p["creator"] = author
    raw = get(NDL + "?" + urllib.parse.urlencode(p), {"User-Agent": "sf-db-probe/1.0"}, sleep=sleep)
    time.sleep(sleep)
    if not raw:
        return out
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return out
    want = norm(title)
    years = []
    for item in root.iter("item"):
        t = item.findtext("title") or ""
        if norm(t) != want and not norm(t).startswith(want):
            continue
        d = item.findtext("dc:date", namespaces=NS) or item.findtext("pubDate") or ""
        m = re.search(r"(1[5-9]\d\d|20\d\d)", d)
        # 出版社が空の書誌は雑誌掲載や典拠レコードのことがあり、単行本の初刊より古い年を
        # 持ち込む(小松左京『継ぐのは誰か?』で1968年を拾った)。年の母数からは外す。
        pub_of = (item.findtext("dc:publisher", namespaces=NS) or "").strip()
        if m and pub_of:
            years.append((int(m.group(1)), pub_of))
        for e in item.iter():
            tag, txt = e.tag, (e.text or "").strip()
            if not txt:
                continue
            if tag.endswith("originalTitle") and not out["orig"]:
                out["orig"] = txt
            elif tag.endswith("titleTranscription") and not out["kana"]:
                out["kana"] = txt
            elif tag.endswith("}publisher") and not out["publisher"]:
                out["publisher"] = txt
            elif tag.endswith("identifier") and not out["isbn"] and re.fullmatch(r"[\d\-Xx]{10,17}", txt):
                out["isbn"] = txt.replace("-", "")
    if years:
        years.sort(key=lambda x: x[0])
        out["first"], out["firstPub"] = years[0]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates")
    ap.add_argument("--sleep", type=float, default=2.0)
    ap.add_argument("--caption", type=int, default=170)
    ap.add_argument("--no-ndl", action="store_true")
    args = ap.parse_args()

    app, key = os.environ.get("RAKUTEN_APP_ID"), os.environ.get("RAKUTEN_ACCESS_KEY")
    if not app or not key:
        sys.exit("RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY が必要です。")

    have = {norm(w["title"]) for w in json.load(open(SRC / "works.json"))}
    lines = [l.strip() for l in Path(args.candidates).read_text(encoding="utf-8").splitlines()]
    cands = [l for l in lines if l and not l.startswith("#")]

    print("n\tst\ttitle\tkana\tauthor\tfirstPub\tndlFirst\tnowPub\tisbn\torigTitle\tcaption")
    for n, line in enumerate(cands, 1):
        title, _, author = line.partition("|")
        title, author = title.strip(), author.strip()
        if norm(title) in have:
            print(f"{n}\tDUP\t{title}")
            continue
        r = rakuten(title, author, app, key)
        time.sleep(0.9)
        nd = {"first": None, "firstPub": "", "orig": None, "kana": "", "publisher": "", "isbn": ""}
        if not args.no_ndl:
            nd = ndl(title, author, args.sleep)
        if not r and not nd["first"] and not nd["publisher"]:
            print(f"{n}\tMISS\t{title}\t\t{author}")
            continue
        cap = re.sub(r"\s+", " ", (r.get("itemCaption") or "") if r else "")
        if not cap:
            cap = re.sub(r"\s+", " ", kobo(title, author, app, key))
            time.sleep(0.6)
        cap = cap[: args.caption]
        kana = re.sub(r"[（(].*?[)）]", "", (r.get("titleKana") or "") if r else "").strip()
        print("\t".join([
            str(n), "OK", title,
            kana or nd["kana"],
            (r.get("author") or "") if r else author,
            nd["firstPub"] or ((r.get("publisherName") or "") if r else ""),
            str(nd["first"] or ""),
            ((r.get("publisherName") or "") if r else ""),
            ((r.get("isbn") or "") if r else "") or nd["isbn"],
            nd["orig"] or "",
            cap,
        ]))


if __name__ == "__main__":
    main()
