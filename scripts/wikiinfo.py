#!/usr/bin/env python3
"""Wikipediaの記事から、導入部(著者・刊行年・版元)とあらすじ節をまとめて取る。

wikicat.py が出した候補を一気に下調べするための道具。1リクエストで20件まとめて取れるので、
plot.py を1件ずつ回すより桁違いに安い。

  python3 scripts/wikiinfo.py titles.txt [--chars 300]

titles.txt は1行1件(記事名)。出力は記事ごとに
  ## 記事名
  LEAD: 導入部(先頭250字)
  PLOT: あらすじ/概要/ストーリー節(先頭 --chars 字)
"""
import argparse, json, re, sys, time, urllib.parse, urllib.request

API = "https://ja.wikipedia.org/w/api.php"
HEADS = ("あらすじ", "ストーリー", "概要", "作品概要", "内容", "プロット")


def fetch(titles, intro=True):
    # prop=extracts は exintro を付けないと1件しか返らない。導入部だけなら20件まとめて取れる。
    p = {"action": "query", "format": "json", "redirects": "1", "prop": "extracts",
         "explaintext": "1", "exlimit": "max", "titles": "|".join(titles)}
    if intro:
        p["exintro"] = "1"
    u = API + "?" + urllib.parse.urlencode(p)
    for _ in range(4):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers={"User-Agent": "sf-db/1.0"}), timeout=90))["query"]["pages"]
        except Exception:
            time.sleep(8)
    return {}


def section(text, chars):
    for h in HEADS:
        m = re.search(r"\n=+ *" + re.escape(h) + r"[^=]* *=+\n", text)
        if m:
            body = text[m.end():]
            nxt = re.search(r"\n=+ [^=]", body)
            if nxt:
                body = body[:nxt.start()]
            body = re.sub(r"\s+", " ", body).strip()
            if len(body) > 40:
                return body[:chars]
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--chars", type=int, default=300)
    ap.add_argument("--lead-only", action="store_true",
                    help="導入部だけを20件まとめて取る(あらすじ節は1件ずつでないと取れない)")
    a = ap.parse_args()
    titles = [l.strip() for l in open(a.file) if l.strip()]
    for i in range(0, len(titles), 20):
        pages = fetch(titles[i:i + 20], intro=a.lead_only)
        got = {}
        for pg in pages.values():
            got[pg["title"]] = pg.get("extract", "") or ""
        for t in titles[i:i + 20]:
            e = got.get(t)
            if e is None:
                # リダイレクト後の名前で入っていることがある
                e = next((v for k, v in got.items() if k.startswith(t[:6])), "")
            lead = re.sub(r"\s+", " ", e.split("\n=")[0]).strip()
            print(f"## {t}")
            print("LEAD: " + (lead[:250] if lead else "NONE"))
            if not a.lead_only:
                print("PLOT: " + (section(e, a.chars) or "NONE"))
        time.sleep(1)


if __name__ == "__main__":
    main()
