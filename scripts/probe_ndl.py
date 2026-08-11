#!/usr/bin/env python3
"""候補タイトルを国立国会図書館サーチAPIで一括下調べする(sf-db版)。

Wikipediaに記事がない小説が大半なので、書誌はこちらが主。probe.py(Wikipedia版)は
映像化の有無やシリーズ情報が欲しいときに補助的に使う。

使い方: python3 scripts/probe.py <candidates.txt> <out.json> [--sleep 3]

candidates.txt は1行1タイトル(空行・# 始まりは無視)。各行について

1. 既存の works.json に同じ本が入っていないか正規化タイトルで照合し、入っていれば DUP として即スキップ
   (詳しく調べる前に弾くことでトークンと時間を節約する)
2. NDLサーチ opensearch API を1件ずつ叩き、書名・書名の読み・責任表示・出版社・刊行年・ISBN13・
   原タイトルを取り出す。同じ書名の全版から最古の年(= firstPublishedYear 候補)も拾う
3. 結果を out.json に保存し、標準出力には1行1件のコンパクトなサマリを出す

NDLは連続アクセスで 429 を返すので、既定3秒間隔・429で指数バックオフする。
"""
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "public" / "data" / "source"
API = "https://ndlsearch.ndl.go.jp/api/opensearch"

NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcndl": "http://ndl.go.jp/dcndl/terms/",
    "dcterms": "http://purl.org/dc/terms/",
}

EDITION_RE = re.compile(r"(第\s*\d+\s*版|改訂\d*版?|改訂新版|新版|増補改訂版?|増補版|完全版|決定版|"
                        r"[0-9]+th\s*edition|\brevised\b)", re.I)


def normalize(s: str) -> str:
    """照合用の正規化。副題・版表記・記号・空白を落として比較しやすくする。"""
    s = unicodedata.normalize("NFKC", s or "")
    s = s.split(":")[0].split("：")[0].split(" - ")[0].split("―")[0]
    s = EDITION_RE.sub("", s)
    s = re.sub(r"[\s　・･,，.。!！?？'\"“”‘’()（）\[\]「」『』【】/／~〜\-—–_+]", "", s)
    return s.lower()


def fetch(params, sleep, tries=4):
    url = API + "?" + urllib.parse.urlencode(params)
    wait = sleep
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sf-db-probe/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < tries - 1:
                wait *= 2
                time.sleep(wait)
                continue
            return None
        except Exception:
            if attempt < tries - 1:
                time.sleep(wait)
                continue
            return None
    return None


def text_of(el, path):
    n = el.find(path, namespaces=NS)
    return (n.text or "").strip() if n is not None and n.text else ""


def year_of(item):
    for path in ("dcterms:issued", "dc:date"):
        v = text_of(item, path)
        m = re.search(r"(19|20)\d{2}", v)
        if m:
            return int(m.group(0))
    return None


def isbn13_of(item):
    for node in item.findall("dc:identifier", namespaces=NS):
        if node.get("{http://www.w3.org/2001/XMLSchema-instance}type") != "dcndl:ISBN":
            continue
        digits = re.sub(r"[^0-9Xx]", "", node.text or "")
        if re.fullmatch(r"97[89]\d{10}", digits):
            return digits
    return None


def responsibility_of(item):
    """description の CDATA に入っている責任表示(「... 著, ... 訳」)を取り出す。"""
    desc = text_of(item, "description") or ""
    m = re.search(r"責任表示：([^<]+)", desc)
    return m.group(1).strip() if m else ""


def original_title_of(item):
    for node in item.findall("dc:description", namespaces=NS):
        t = (node.text or "").strip()
        m = re.match(r"原タイトル\s*[:：]\s*(.+)", t)
        if m:
            return re.sub(r"\s*(原著第?\d+版|第\d+版).*$", "", m.group(1)).strip()
    return ""


def publisher_of(item):
    pubs = [(n.text or "").strip() for n in item.findall("dc:publisher", namespaces=NS)]
    pubs = [p for p in pubs if p and "発売" not in p]
    return pubs[0] if pubs else ""


def parse(xml, want):
    """候補タイトル want に合致する版を集める。"""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    key = normalize(want)
    out = []
    for item in root.iter("item"):
        cats = [(c.text or "") for c in item.findall("category")]
        if cats and "図書" not in cats:
            continue
        title = text_of(item, "dc:title")
        nt = normalize(title)
        if not nt or (key not in nt and nt not in key):
            continue
        out.append({
            "title": title,
            "kana": text_of(item, "dcndl:titleTranscription"),
            "year": year_of(item),
            "isbn": isbn13_of(item),
            "publisher": publisher_of(item),
            "resp": responsibility_of(item),
            "originalTitle": original_title_of(item),
        })
    return out


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cand_path, out_path = sys.argv[1], sys.argv[2]
    sleep = 3.0
    if "--sleep" in sys.argv:
        sleep = float(sys.argv[sys.argv.index("--sleep") + 1])
    workers = 1
    if "--workers" in sys.argv:
        workers = int(sys.argv[sys.argv.index("--workers") + 1])

    works = json.load(open(SRC / "works.json", encoding="utf-8"))
    existing = {}
    for w in works:
        existing.setdefault(normalize(w["title"]), w["id"])

    lines = [ln.strip() for ln in open(cand_path, encoding="utf-8")]
    cands = [ln for ln in lines if ln and not ln.startswith("#")]

    def probe_one(i, cand):
        # "タイトル|著者" 形式に対応する。著者は検索の絞り込みだけに使い、重複判定はタイトルで行う
        creator = ""
        if "|" in cand:
            cand, creator = [x.strip() for x in cand.split("|", 1)]
        key = normalize(cand)
        hit = existing.get(key)
        if hit is None:
            for k, wid in existing.items():
                if k and (k in key or key in k) and abs(len(k) - len(key)) <= 2:
                    hit = wid
                    break
        if hit:
            return {"n": i, "query": cand, "status": "DUP", "existingId": hit}

        # mediatype は指定しないこと。`mediatype=1` を付けると図書がヒット0件になる(実際に踏んだ)
        q = {"title": cand, "cnt": "30"}
        if creator:
            q["creator"] = creator
        xml = fetch(q, sleep)
        time.sleep(sleep)
        editions = parse(xml or "", cand)
        if not editions:
            return {"n": i, "query": cand, "status": "MISS"}

        with_isbn = [e for e in editions if e["isbn"]]
        pick = max(with_isbn or editions, key=lambda e: (e["year"] or 0))
        years = [e["year"] for e in editions if e["year"]]
        return {
            "n": i, "query": cand, "status": "OK",
            "first_year": min(years) if years else None,
            "edition_count": len(editions), **pick,
        }

    def render(r):
        if r["status"] == "DUP":
            return f"{r['n']}\tDUP\t{r['query']}\t-> {r['existingId']}"
        if r["status"] == "MISS":
            return f"{r['n']}\tMISS\t{r['query']}"
        return (f"{r['n']}\tOK\t{r['title']}\t{r['kana']}\t{r['resp']}\t{r['publisher']}\t"
                f"{r['year']}\tfirst={r['first_year']}\t{r['isbn']}\t{r['originalTitle']}")

    # NDLは1件5〜18秒かかる(待ちの大半はレスポンス待ち)ので、少数のワーカーで並行に投げる。
    if workers > 1:
        # 完了順に出す(pool.map だと全件終わるまで1行も出ず、進捗が見えない)
        results = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(probe_one, i, c) for i, c in enumerate(cands, 1)]
            for f in as_completed(futures):
                r = f.result()
                results.append(r)
                print(render(r), flush=True)
        results.sort(key=lambda r: r["n"])
    else:
        results = []
        for i, cand in enumerate(cands, 1):
            r = probe_one(i, cand)
            results.append(r)
            print(render(r), flush=True)

    Path(out_path).write_text(
        json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    n_ok = sum(1 for r in results if r["status"] == "OK")
    n_dup = sum(1 for r in results if r["status"] == "DUP")
    print(f"\n-- OK={n_ok} DUP={n_dup} MISS={len(results)-n_ok-n_dup} -> {out_path}")


if __name__ == "__main__":
    main()
