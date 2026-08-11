#!/usr/bin/env python3
"""probe.py の下調べ結果と手書きの注釈を合成して apply_batch.py 用の batch.json を作る。

使い方: python3 scripts/merge_batch.py <probe.json> <annot.json> <batch.json>

annot.json(キーを短くしてあるのは手書き量を減らすため):
{
  "newAuthors":     [{"id":..,"name":..,"kana":..,"desc":..,"birth":1890?}],
  "newTranslators": [{"id":..,"name":..,"kana":..,"desc":..}],
  "newPublishers":  [{"id":..,"name":..,"kana":..,"desc":..}],
  "newThemes":      [{"id":..,"name":..,"desc":..,"spoiler":true?}],
  "newAwards":      [{"id":..,"name":..,"description":..}],
  "works": [
    {"n": 3, "id": "nihon-chinbotsu", "a": ["komatsu-sakyo"],
     "tr": ["tanaka-taro"], "p": "hayakawa-shobo", "th": ["hard-sf","kikou-sf"],
     "o": "jp",              # "jp" | "ov"
     "fy": 1947,             # 原著発表年(省略時は probe の year)
     "jy": 1953,             # 邦訳初刊年(海外作品のみ)
     "ot": "The ...",        # 原題(海外作品は必須)
     "series": "…シリーズ", "status": "completed",
     "mm": {"movie":true,"drama":true,"anime":false,"comic":false},   # 省略時は probe の推定
     "awards": [{"awardId":..,"year":..,"result":..}],
     "title": "…", "kana": "…",   # probe の値を上書きしたいときだけ
     "syn": "…"}             # 150〜250字。ネタバレ厳禁(CLAUDE.mdのネタバレ方針を参照)
  ]
}
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "public" / "data" / "source"
TODAY = "2026-08-07"


def norm(s: str) -> str:
    return re.sub(r"[\s　・･,，.。]", "", unicodedata.normalize("NFKC", s or "")).lower()


def kata_to_hira(s: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def short_title(raw: str) -> str:
    return raw.split(" : ")[0].split("：")[0].strip()


def title_kana(raw: str) -> str:
    s = short_title(raw)
    return re.sub(r"[\s　]", "", kata_to_hira(unicodedata.normalize("NFKC", s))).lower()


def loose(s: str) -> str:
    s = norm(s)
    s = re.sub(r"[(（].*?[)）]", "", s)
    return re.sub(r"(株式会社|出版|書店|社)$", "", s)


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    probe = {r["n"]: r for r in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))}
    annot = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    out_path = Path(sys.argv[3])

    publishers = json.loads((SRC / "publishers.json").read_text(encoding="utf-8"))
    pub_by = {norm(p["name"]): p["id"] for p in publishers}
    pub_loose = {loose(p["name"]): p["id"] for p in publishers}

    batch = {"newAuthors": [], "newTranslators": [],
             "newPublishers": [], "newThemes": [], "newAwards": [], "works": []}

    def person(x):
        d = {"id": x["id"], "name": x["name"], "nameKana": x["kana"], "description": x["desc"],
             "externalLinks": {}, "sourceNote": x.get("note", "日本語版Wikipediaの当該人物・作品記事で確認。"),
             "updatedAt": TODAY}
        if x.get("birth"):
            d["birthYear"] = x["birth"]
        return d

    for x in annot.get("newAuthors", []):
        batch["newAuthors"].append(person(x))
    for x in annot.get("newTranslators", []):
        batch["newTranslators"].append(person(x))
    for x in annot.get("newPublishers", []):
        batch["newPublishers"].append(person(x))
        pub_by[norm(x["name"])] = x["id"]
        pub_loose.setdefault(loose(x["name"]), x["id"])
    for x in annot.get("newThemes", []):
        t = {"id": x["id"], "name": x["name"], "description": x.get("desc", ""), "updatedAt": TODAY}
        if x.get("spoiler"):
            t["spoiler"] = True
        batch["newThemes"].append(t)
    for x in annot.get("newAwards", []):
        batch["newAwards"].append(x)

    problems = []
    for a in annot.get("works", []):
        p = probe.get(a["n"])
        if p is None or p.get("status") != "OK":
            problems.append(f"n={a['n']} ({a.get('id')}): probeにOKの結果がない")
            continue
        ndl = "page" not in p  # probe_ndl.py(国立国会図書館サーチ)の結果か
        overseas = a.get("o") == "ov"
        pid = a.get("p") or pub_by.get(norm(p.get("publisher", ""))) or pub_loose.get(loose(p.get("publisher", "")))
        if not pid:
            problems.append(f"n={a['n']} ({a['id']}): 出版社 {p.get('publisher')!r} を解決できない")
            continue
        fy = a.get("fy") or (p.get("first_year") if ndl else p.get("year"))
        if not fy:
            problems.append(f"n={a['n']} ({a['id']}): 発表年が取れない(fy を指定)")
            continue
        if not a.get("a"):
            problems.append(f"n={a['n']} ({a['id']}): authorIds が空")
            continue
        w = {
            "id": a["id"],
            "title": a.get("title") or (short_title(p["title"]) if ndl
                                        else re.sub(r"\s*[(（][^)）]*[)）]\s*$", "", p["page"])),
            "titleKana": a.get("kana") or (title_kana(p.get("kana") or "") if ndl else p.get("kana") or ""),
            "authorIds": a["a"],
            "translatorIds": a.get("tr", []) if overseas else [],
            "publisherId": pid,
            "themeIds": a.get("th", []),
            "origin": "overseas" if overseas else "jp",
            "firstPublishedYear": fy,
            "status": a.get("status", "completed"),
            "synopsis": a.get("syn", ""),
            "mediaMix": a.get("mm") or {"movie": bool(p.get("movie")), "drama": bool(p.get("drama")),
                                        "anime": bool(p.get("anime")), "comic": bool(p.get("comic"))},
            "externalLinks": {} if ndl else {"wikipediaUrl": p["url"]},
            "updatedAt": TODAY,
        }
        if a.get("series"):
            w["seriesName"] = a["series"]
        if overseas:
            ot = a.get("ot") or p.get("origTitle")
            if not ot:
                problems.append(f"n={a['n']} ({a['id']}): 海外作品は原題 ot が必要")
                continue
            w["originalTitle"] = ot
            if a.get("jy"):
                w["jpPublishedYear"] = a["jy"]
        if a.get("awards"):
            w["awardResults"] = a["awards"]
        if ndl:
            note = (f"書誌({p.get('publisher')}、{p.get('year')}年"
                    + (f"、ISBN {p['isbn']}" if p.get("isbn") else "") + ")は"
                    "国立国会図書館サーチAPI(opensearch)の検索結果で確認。")
            if p.get("resp"):
                note += f"著者・訳者は同APIの責任表示「{p['resp']}」による。"
            if p.get("first_year") and p.get("first_year") != p.get("year"):
                note += f"初刊年{p['first_year']}年は同APIで同書名の全版を引いて確認。"
        else:
            note = f"日本語版Wikipedia『{p['page']}』記事(2026-08-07閲覧)で著者・発表年"
            note += "・原題" if overseas else ""
            note += "・映像化の有無を確認。"
        note += "あらすじは独自要約(コピペなし、真相・トリックには触れていない)。"
        w["sourceNote"] = a.get("note") or note
        batch["works"].append(w)

    out_path.write_text(json.dumps(batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"works={len(batch['works'])} authors={len(batch['newAuthors'])} "
          f"translators={len(batch['newTranslators'])} "
          f"publishers={len(batch['newPublishers'])} -> {out_path}")
    if problems:
        print("-- 未反映 --")
        for x in problems:
            print(" ", x)


if __name__ == "__main__":
    main()
