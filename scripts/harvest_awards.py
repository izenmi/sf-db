#!/usr/bin/env python3
"""awards.json の各賞について、Wikipediaの賞ページから受賞作がどれだけ機械抽出できるかを調べる**下見用**ツール。

**--list(下見)以外は使わないこと。**汎用の列推定は賞ページの書式差に耐えられず、
「第1回」「受賞」「候補」「著者名」をタイトルとして拾ってしまう(日本推理作家協会賞・直木賞・
大藪春彦賞で実際に確認)。**実際の取り込みは賞ごとに書式を見てから使い捨てスクリプトで行う**
(このミス・このマンガ・全国書店員・手塚治虫文化賞・ITエンジニア本大賞はいずれもその方式で処理した)。
候補・ノミネート行を混入させないためにも、賞ごとの目視確認は省略できない。

  python3 scripts/harvest_awards.py --list                 # 賞ごとの抽出可否だけ見る
  python3 scripts/harvest_awards.py --apply <awardId> …    # 付与を実行(省略時は全賞)
  python3 scripts/harvest_awards.py --cand out.tsv         # 未登録候補を書き出す

賞ページは表形式・箇条書き・年ごとの節など形式がまちまちなので、
**表(wikitable)と箇条書きの両方を試して、取れたほうを使う**。どちらでも取れない賞は
レポートに出すので、その賞だけ使い捨てスクリプトで処理すればよい。

works.json(game-dbはgames.json)とはタイトル正規化で突き合わせる。
『64（ロクヨン）』のような括弧併記に備えて、括弧を外した形・中身だけの形でも照合する。
"""
import argparse
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "public" / "data" / "source"
TODAY = "2026-08-07"
DROP = re.compile(r"[\s　ー～〜~\-−–—・,、.。!！?？:：;；'\"’”“‘()（）\[\]【】<>《》「」『』/／\\|＃#]")


def norm(s):
    return DROP.sub("", unicodedata.normalize("NFKC", s or "").lower())


def variants(t):
    v = {t, re.sub(r"[（(][^）)]*[）)]", "", t).strip()}
    m = re.search(r"[（(]([^）)]*)[）)]", t)
    if m:
        v.add(m.group(1).strip())
    return {norm(x) for x in v if x}


def fetch(page):
    url = "https://ja.wikipedia.org/wiki/" + urllib.parse.quote(page) + "?action=raw"
    req = urllib.request.Request(url, headers={"User-Agent": "db-award-harvest/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode("utf-8")
    except Exception:
        return ""


def clean(s):
    s = re.sub(r"<ref[^>/]*/>", "", s)
    s = re.sub(r"<ref.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"\{\{仮リンク\|([^|}]+)[^}]*\}\}", r"\1", s)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s{2,}", " ", s).replace("'''", "").strip()


def rows_from_tables(wt):
    """wikitableの各行から (年, 賞区分, タイトル, 著者) を推定して取り出す。"""
    out = []
    year = None
    for block in re.findall(r"\{\|.*?\n\|\}", wt, flags=re.S):
        for line in block.splitlines():
            st = line.strip()
            m = re.match(r"^!\s*colspan=[^|]*\|\s*((19|20)\d{2})", st)
            if m:
                year = m.group(1)
                continue
            if not st.startswith("|") or st.startswith("|-") or st.startswith("|}") or st.startswith("|+"):
                continue
            cells = [clean(re.sub(r"^[^|\[\]{}]*=[^|]*\|(?!\|)", "", c)) for c in re.split(r"\|\|", st.lstrip("|"))]
            cells = [c for c in cells if c]
            if len(cells) < 2:
                continue
            y = year
            for c in cells:
                m = re.search(r"((19|20)\d{2})年", c)
                if m:
                    y = m.group(1)
                    break
            title = next((c for c in cells if not re.fullmatch(r"[\d 位第回年（）()\-–]+", c)), "")
            if not y or not title:
                continue
            out.append({"year": int(y), "title": title,
                        "author": cells[cells.index(title) + 1] if cells.index(title) + 1 < len(cells) else "",
                        "result": cells[0] if cells[0] != title else "受賞"})
    return out


def rows_from_lists(wt):
    """『* [[作品]]（著者）』形式の箇条書きから取り出す。直近の見出しから年を引き継ぐ。"""
    out = []
    year = None
    for line in wt.splitlines():
        st = line.strip()
        m = re.match(r"^=+\s*(.+?)\s*=+$", st)
        if m:
            y = re.search(r"((19|20)\d{2})年", m.group(1))
            year = y.group(1) if y else year
            continue
        m = re.match(r"^'''第\s*\d+\s*回'''（\[?\[?((19|20)\d{2})年", st)
        if m:
            year = m.group(1)
            continue
        if not re.match(r"^[*#]\s*", st) or not year:
            continue
        body = clean(re.sub(r"^[*#]+\s*", "", st))
        m = re.match(r"^(.+?)[（(]([^）)]*)[）)]\s*$", body)
        if not m:
            continue
        title, author = m.group(1).strip(), m.group(2).strip()
        title = re.sub(r"^(受賞|大賞|優秀賞|佳作)[:：]\s*", "", title)
        if len(title) < 2:
            continue
        out.append({"year": int(year), "title": title, "author": author, "result": "受賞"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", nargs="*", default=None)
    ap.add_argument("--cand", default="")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    works_path = SRC / "works.json"
    if not works_path.exists():
        works_path = SRC / "games.json"
    works = json.load(open(works_path, encoding="utf-8"))
    awards = json.load(open(SRC / "awards.json", encoding="utf-8"))
    idx = {}
    for w in works:
        for k in variants(w["title"]):
            idx.setdefault(k, w)

    targets = awards if args.apply in (None, []) else [a for a in awards if a["id"] in args.apply]
    cand_rows, total_added, touched = [], 0, set()
    for a in targets:
        wt = fetch(a["name"])
        rows = rows_from_tables(wt) or rows_from_lists(wt)
        hit = [r for r in rows if any(k in idx for k in variants(r["title"]))]
        print(f"{a['id']}\t抽出{len(rows)}\t既登録一致{len(hit)}\t未登録{len(rows)-len(hit)}")
        if args.list:
            continue
        for r in rows:
            w = next((idx[k] for k in variants(r["title"]) if k in idx), None)
            if not w:
                cand_rows.append((a["id"], r))
                continue
            rec = {"awardId": a["id"], "year": r["year"], "result": r["result"] or "受賞"}
            ar = w.setdefault("awardResults", [])
            if not any(x["awardId"] == rec["awardId"] and x["year"] == rec["year"] for x in ar):
                ar.append(rec)
                total_added += 1
                touched.add(w["id"])
    if args.list:
        return
    for w in works:
        if w["id"] in touched:
            w["awardResults"] = sorted(w["awardResults"], key=lambda x: (x["year"], x["result"]))
            w["updatedAt"] = TODAY
    json.dump(works, open(works_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(works_path, "a", encoding="utf-8").write("\n")
    print(f"-- 付与 {total_added}件 / {len(touched)}作品")
    if args.cand:
        with open(args.cand, "w", encoding="utf-8") as f:
            for aid, r in cand_rows:
                f.write(f"{r['title']}\t{r['author']}\t{r['result']}\t{r['year']}\t{aid}\n")
        print(f"-- 未登録候補 {len(cand_rows)}件 -> {args.cand}")


if __name__ == "__main__":
    main()
