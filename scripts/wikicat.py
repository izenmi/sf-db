#!/usr/bin/env python3
"""日本語版WikipediaのSF小説カテゴリから、works.json 未登録の作品を列挙する。

賞のページを一巡したあとの候補源。個別記事がある作品だけが並ぶので、
(1) 実在確認が済んでいる (2) あらすじ節を plot.py で引ける、の二点が同時に満たせる。

  python3 scripts/wikicat.py                 # 既定のカテゴリを全部見る
  python3 scripts/wikicat.py 日本のSF小説     # カテゴリを指定

出力(TSV): st / カテゴリ / 記事名 / 曖昧さ回避を除いた表示名
"""
import json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from award_wiki import norm

SRC = Path(__file__).resolve().parent.parent / "public" / "data" / "source"
DEFAULT = [
    "日本のSF小説", "SF小説", "アメリカ合衆国のSF小説", "イギリスのSF小説",
    "アメリカ合衆国のSFホラー小説", "イギリスのSFホラー小説",
    "ロシアのSF小説", "フランスのSF小説", "ドイツのSF小説", "中国のSF小説",
    "カナダのSF小説", "ポーランドのSF小説", "韓国のSF小説",
]


def members(cat):
    out, cont = [], None
    while True:
        p = {"action": "query", "format": "json", "list": "categorymembers",
             "cmtitle": "Category:" + cat, "cmlimit": "500", "cmnamespace": "0"}
        if cont:
            p["cmcontinue"] = cont
        u = "https://ja.wikipedia.org/w/api.php?" + urllib.parse.urlencode(p)
        for _ in range(4):
            try:
                d = json.load(urllib.request.urlopen(
                    urllib.request.Request(u, headers={"User-Agent": "sf-db/1.0"}), timeout=60))
                break
            except Exception:
                time.sleep(6)
        else:
            return out
        out += [m["title"] for m in d.get("query", {}).get("categorymembers", [])]
        cont = d.get("continue", {}).get("cmcontinue")
        if not cont:
            return out
        time.sleep(0.5)


def main():
    works = json.loads((SRC / "works.json").read_text())
    known = {norm(w["title"]) for w in works}
    cats = sys.argv[1:] or DEFAULT
    n = d = 0
    for cat in cats:
        for title in members(cat):
            disp = re.sub(r"\s*\([^)]*\)$", "", title).strip()
            st = "DUP" if norm(disp) in known else "new"
            if st == "new":
                n += 1
            else:
                d += 1
            print(f"{st}\t{cat}\t{title}\t{disp}")
        time.sleep(1)
    print(f"-- new={n} dup={d}", file=sys.stderr)


if __name__ == "__main__":
    main()
