#!/usr/bin/env python3
"""候補タイトルを日本語版Wikipedia APIで一括下調べする。

使い方: python3 scripts/probe.py <candidates.txt> <out.json> [--sleep 0.4] [--workers 4]

candidates.txt は1行1タイトル(空行・# 始まりは無視)。各行について

1. 既存の works.json と正規化タイトルで照合し、登録済みなら DUP として即スキップ
   (詳しく調べる前に弾くことでトークンと時間を節約する)
2. Wikipedia API で記事を検索 → wikitext を取得し、書籍系のInfoboxから
   著者・訳者・出版社・原題・発表年・ジャンル・シリーズを取り出す
3. 記事本文から映画化・ドラマ化・アニメ化・漫画化の有無を推定する(mediaMix の下書き)
4. 結果を out.json に保存し、標準出力には1行1件のコンパクトなサマリを出す

**注意**: あらすじ・テーマ・探偵は自動では取れない。probe はあくまで書誌の下調べで、
ネタバレ方針に沿ったあらすじは必ず自分の言葉で書くこと。
"""
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "public" / "data" / "source"
API = "https://ja.wikipedia.org/w/api.php"
UA = "sf-db-probe/1.0 (https://izenmi.github.io/sf-db/)"


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"[(（].*?[)）]", "", s)
    s = re.sub(r"[\s　・･,，.。!！?？'\"“”‘’\[\]「」『』【】/／~〜\-—–_+:：]", "", s)
    return s.lower()


def kata_to_hira(s: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def api(params, tries=3):
    params = {**params, "format": "json", "formatversion": "2"}
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if attempt < tries - 1:
                time.sleep(1 + attempt)
                continue
            return None
    return None


def strip_markup(v: str) -> str:
    v = re.sub(r"<ref[^>]*?/>", "", v)
    v = re.sub(r"<ref.*?</ref>", "", v, flags=re.S)
    v = re.sub(r"<br\s*/?>", " / ", v, flags=re.I)
    v = re.sub(r"<!--.*?-->", "", v, flags=re.S)
    v = re.sub(r"\{\{(?:仮リンク|Anchors?|要出典|small|Small|lang|Lang)\|(?:[a-z\-]+\|)?([^|}]*)[^}]*\}\}", r"\1", v)
    v = re.sub(r"\{\{[^{}]*\}\}", "", v)
    v = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]|]*)\]\]", r"\1", v)
    v = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", v)
    v = re.sub(r"</?[a-zA-Z][^>]*>", "", v)
    v = v.replace("'''", "").replace("''", "")
    return re.sub(r"\s+", " ", v).strip(" 　-–—,、")


def drop_templates(text: str) -> str:
    out, depth, i = [], 0, 0
    while i < len(text):
        if text.startswith("{{", i):
            depth += 1
            i += 2
            continue
        if text.startswith("}}", i):
            depth = max(0, depth - 1)
            i += 2
            continue
        if depth == 0:
            out.append(text[i])
        i += 1
    return "".join(out)


BOLD = "'" * 3
LEAD_KANA_RE = re.compile(BOLD + r"\s*[^']{1,60}?\s*" + BOLD + r"[』」]?\s*[（(]([ぁ-んァ-ヶー・\s]{2,60})[）)]")
YOMI_RE = re.compile(r"\{\{読み仮名[^|]*\|[^|]*\|([ぁ-んァ-ヶー・\s]{2,60})[|}]")

INFOBOX_RE = re.compile(r"\{\{\s*(Infobox[ _]book|基礎情報[ _]書籍|Infobox[ _]Book|Infobox[ _]animanga/Novel)", re.I)


def parse_infobox(text: str):
    m = INFOBOX_RE.search(text)
    if not m:
        return {}
    i = m.end()
    depth, buf = 2, []
    while i < len(text) and depth > 0:
        if text.startswith("{{", i):
            depth += 2
            buf.append("{{")
            i += 2
            continue
        if text.startswith("}}", i):
            depth -= 2
            if depth <= 0:
                break
            buf.append("}}")
            i += 2
            continue
        buf.append(text[i])
        i += 1
    body = "".join(buf)
    fields, depth2, cur = {}, 0, ""
    for ch in body:
        if ch in "{[":
            depth2 += 1
        elif ch in "}]":
            depth2 -= 1
        if ch == "|" and depth2 <= 0:
            if "=" in cur:
                k, _, v = cur.partition("=")
                fields[k.strip().lower()] = v.strip()
            cur = ""
        else:
            cur += ch
    if "=" in cur:
        k, _, v = cur.partition("=")
        fields[k.strip().lower()] = v.strip()
    return fields


YEAR_RE = re.compile(r"(1[6-9]\d{2}|20[0-2]\d)")


def first_year(*values):
    for v in values:
        if not v:
            continue
        m = YEAR_RE.search(strip_markup(v))
        if m:
            return int(m.group(0))
    return None


def get(fields, *keys):
    for k in keys:
        if k in fields and fields[k].strip():
            return strip_markup(fields[k])
    return ""


def probe_one(i, cand, existing, sleep):
    # "タイトル|著者名" 形式を許す。著者名は検索の曖昧さ回避にだけ使い、重複判定はタイトルのみで行う
    title, _, hint = cand.partition("|")
    title, hint = title.strip(), hint.strip()
    key = normalize(title)
    hit = existing.get(key)
    if hit is None:
        for k, wid in existing.items():
            if k and (k in key or key in k) and abs(len(k) - len(key)) <= 2:
                hit = wid
                break
    if hit:
        return {"n": i, "query": title, "status": "DUP", "existingId": hit}

    search = api({"action": "query", "list": "search", "srsearch": (title + " " + hint).strip(),
                  "srlimit": "3", "srnamespace": "0"})
    time.sleep(sleep)
    hits = ((search or {}).get("query") or {}).get("search") or []
    if not hits:
        return {"n": i, "query": title, "status": "MISS"}
    page = next((h["title"] for h in hits
                 if normalize(h["title"]) == key or key in normalize(h["title"])), hits[0]["title"])
    if normalize(page) in existing:
        return {"n": i, "query": title, "status": "DUP", "existingId": existing[normalize(page)]}

    rev = api({"action": "query", "prop": "revisions", "rvprop": "content",
               "rvslots": "main", "titles": page})
    time.sleep(sleep)
    try:
        text = rev["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]
    except Exception:
        return {"n": i, "query": title, "status": "MISS"}
    if re.match(r"^\s*#(REDIRECT|転送)", text, re.I):
        m = re.search(r"\[\[([^\]|]+)", text)
        if m:
            page = m.group(1)
            rev = api({"action": "query", "prop": "revisions", "rvprop": "content",
                       "rvslots": "main", "titles": page})
            time.sleep(sleep)
            try:
                text = rev["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]
            except Exception:
                return {"n": i, "query": title, "status": "MISS"}

    # 作品記事ではなく人物記事に流れてしまった場合は採用しない
    if hint and normalize(page) == normalize(hint):
        return {"n": i, "query": title, "status": "MISS"}
    lead1 = drop_templates(text[:6000]).lstrip().split("。")[0][:200]
    if re.search(r"(?:小説家|推理作家|作家|評論家|翻訳家|漫画家)(?:・[^、]{0,10})?$", lead1):
        return {"n": i, "query": title, "status": "MISS"}

    f = parse_infobox(text)
    body = drop_templates(text[:14000])
    m = LEAD_KANA_RE.search(body) or YOMI_RE.search(text[:6000])
    kana = re.sub(r"[\s　・]", "", kata_to_hira(m.group(1))) if m else ""

    author = get(f, "著者", "author", "作者", "原作")
    translator = get(f, "訳者", "translator", "翻訳")
    publisher = get(f, "出版社", "publisher", "発行元", "刊行")
    orig_title = get(f, "原題", "orig_title", "orig title", "original_title")
    genre = get(f, "ジャンル", "genre")
    series = get(f, "シリーズ", "series")
    y_orig = first_year(f.get("発表年"), f.get("刊行"), f.get("release_date"), f.get("発行日"),
                        f.get("出版年"), f.get("published"))
    y_jp = first_year(f.get("日本語版出版年"), f.get("japanese_release_date"), f.get("翻訳出版"))

    head = drop_templates(text[:5000])
    if not y_orig:
        y_orig = first_year(head)

    # Infoboxを持たない記事が多いので、冒頭文からも著者・原題・国籍を拾う
    if not author:
        m2 = re.search(r"は、?\s*(?:\[\[)?([^\[\]。、（(]{2,24}?)(?:\]\])?\s*(?:による|の(?:長編|短編)?(?:推理)?小説)", head)
        if m2:
            author = strip_markup(m2.group(1))
            if re.search(r"[=|<>\n]|^\s*$", author) or len(author) > 20:
                author = ""
    if not orig_title:
        m3 = re.search(r"原題[:：\s]*[『「]?([A-Za-z0-9''’&,.:!?\-\s]{3,70})[』」]?", head)
        if m3:
            orig_title = m3.group(1).strip(" 　'\"")
    overseas = bool(re.search(r"原題|翻訳|訳者|アメリカ|イギリス|フランス|スウェーデン|作家[^。]{0,20}(?:による)?の(?:長編)?(?:推理)?小説", head)) \
        and not re.search(r"日本の(?:長編|短編)?(?:推理|ミステリ|小説)", head)
    if re.search(r"日本の", head[:400]):
        overseas = False

    return {
        "n": i, "query": title, "status": "OK", "page": page, "kana": kana,
        "author": author, "translator": translator, "publisher": publisher,
        "origTitle": orig_title, "genre": genre, "series": series, "overseas": overseas,
        "year": y_orig, "jpYear": y_jp,
        "movie": bool(re.search(r"映画化|劇場版", text)),
        "drama": bool(re.search(r"テレビドラマ|ドラマ化|連続ドラマ", text)),
        "anime": bool(re.search(r"アニメ化|テレビアニメ", text)),
        "comic": bool(re.search(r"漫画化|コミカライズ|コミック版", text)),
        "url": "https://ja.wikipedia.org/wiki/" + urllib.parse.quote(page.replace(" ", "_")),
    }


def render(r):
    if r["status"] == "DUP":
        return f"{r['n']}\tDUP\t{r['query']}\t-> {r['existingId']}"
    if r["status"] == "MISS":
        return f"{r['n']}\tMISS\t{r['query']}"
    mm = "".join(c for c, k in (("映", "movie"), ("ド", "drama"), ("ア", "anime"), ("漫", "comic")) if r[k])
    return (f"{r['n']}\tOK\t{r['page']}\t{r['kana']}\t{r['author']}\t{r['publisher']}\t"
            f"{r['year']}\t{'海外' if r['overseas'] else '国内'}\t{r['origTitle'][:40]}\t{mm}\t{r['genre'][:16]}")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cand_path, out_path = sys.argv[1], sys.argv[2]
    sleep = float(sys.argv[sys.argv.index("--sleep") + 1]) if "--sleep" in sys.argv else 0.4
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 4

    works = json.load(open(SRC / "works.json", encoding="utf-8"))
    existing = {}
    for w in works:
        existing.setdefault(normalize(w["title"]), w["id"])

    cands = [ln.strip() for ln in open(cand_path, encoding="utf-8")]
    cands = [c for c in cands if c and not c.startswith("#")]

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(probe_one, i, c, existing, sleep) for i, c in enumerate(cands, 1)]
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            print(render(r), flush=True)
    results.sort(key=lambda r: r["n"])
    Path(out_path).write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    ok = sum(1 for r in results if r["status"] == "OK")
    dup = sum(1 for r in results if r["status"] == "DUP")
    print(f"\n-- OK={ok} DUP={dup} MISS={len(results)-ok-dup} -> {out_path}")


if __name__ == "__main__":
    main()
