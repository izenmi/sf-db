#!/usr/bin/env python3
"""prep.py の結果 + 手書きの注釈TSV から apply_batch.py 用の batch.json を組み立てる(sf-db版)。

  python3 scripts/gen_batch.py prep.json anno.tsv batch.json 江戸川乱歩賞

anno.tsv(1行1作品、タブ区切り):
  <n> <themeIds(カンマ区切り)> <あらすじ(自分の言葉で要約、真相に触れない)> [<flags>] [<overrides>]
    flags     … v=海外作品(origin=overseas。訳者と原題をNDLから解決する),
                m=映像化(映画), d=ドラマ化, a=アニメ化, c=コミカライズ, o=ongoing(シリーズ継続中),
                x=採用しない, n=あらすじの典拠が無く内容未確認
    overrides … title / kana / pub(=publisherId) / author(名前、カンマ区切り) / year / id /
                award / result / ayear / series(=seriesName)

ranobe-db版との違い: イラストレーターと巻数を持たず、代わりに translatorIds /
origin / seriesName / mediaMix{movie,drama,anime,comic} を持つ。出版社はレーベルではなく版元。
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import time
import urllib.parse
import xml.etree.ElementTree as ET

from prep import NDL, NS, clean_person, get, hiragana, norm, romaji  # noqa: E402


def kana_lookup(name, cache):
    """著者名の読みをNDLの著者検索から引く(id採番と nameKana 用)。"""
    if name in cache:
        return cache[name]
    xml = get(NDL + "?" + urllib.parse.urlencode({"creator": name, "cnt": "10"}), sleep=2)
    time.sleep(1.2)
    got = ""
    if xml:
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            root = None
        if root is not None:
            for item in (root.iter("item") if root is not None else []):
                cs = [clean_person(n.text) for n in item.findall("dc:creator", namespaces=NS)]
                ts = [clean_person(n.text) for n in item.findall("dcndl:creatorTranscription", namespaces=NS)]
                for c, t in zip(cs, ts):
                    if norm(c) == norm(name) and t:
                        got = hiragana(t).replace(" ", "")
                        break
                if got:
                    break
    cache[name] = got
    return got

SRC = Path(__file__).resolve().parent.parent / "public" / "data" / "source"
TODAY = "2026-08-07"

SOURCE_NOTE = ("書名・著者・出版社・刊行年は国立国会図書館サーチAPI(opensearch)の書誌で、受賞歴は"
               "Wikipedia日本語版「{award}」の受賞作一覧で確認({date}照会)。あらすじは版元の紹介文および"
               "Wikipedia記事を参考にした独自要約(コピペなし、真相・トリックには触れていない)。")


def load(name):
    return json.load(open(SRC / f"{name}.json", encoding="utf-8"))


def main():
    prep_path, anno_path, out_path = sys.argv[1:4]
    award_name = sys.argv[4] if len(sys.argv) > 4 else "各賞"
    prep = {r["n"]: r for r in json.load(open(prep_path, encoding="utf-8"))}

    authors, publishers = load("authors"), load("publishers")
    translators = load("translators")
    translator_by_name = {norm(t["name"]): t["id"] for t in translators}
    translator_ids_taken = {t["id"] for t in translators}
    new_translators = []
    themes, works = load("themes"), load("works")
    author_by_name = {norm(a["name"]): a["id"] for a in authors}
    pub_by_name = {}
    for p in publishers:
        # publishers.json は「KADOKAWA(角川書店)」のように別称を括弧書きで持つので、
        # 括弧の前後どちらの表記でもNDLの出版社名と突き合わせられるようにする
        pub_by_name[norm(p["name"])] = p["id"]
        m = re.match(r"^([^（(]+)[（(]([^）)]+)[）)]", p["name"])
        if m:
            pub_by_name.setdefault(norm(m.group(1)), p["id"])
            pub_by_name.setdefault(norm(m.group(2)), p["id"])
    theme_ids = {t["id"] for t in themes}
    work_ids = {w["id"] for w in works}
    author_ids_taken = {a["id"] for a in authors}

    kana_cache_path = Path(__file__).resolve().parent.parent / ".kana-cache.json"
    kana_cache = json.loads(kana_cache_path.read_text(encoding="utf-8")) if kana_cache_path.exists() else {}
    new_authors, out_works, problems = [], [], []

    def uniq_id(base, taken):
        base = base or "work"
        cand, i = base, 2
        while cand in taken:
            cand = f"{base}-{i}"
            i += 1
        taken.add(cand)
        return cand

    for ln in open(anno_path, encoding="utf-8"):
        ln = ln.rstrip("\n")
        if not ln.strip() or ln.startswith("#"):
            continue
        f = ln.split("\t")
        n = int(f[0])
        theme_str = f[1] if len(f) > 1 else ""
        synopsis = f[2] if len(f) > 2 else ""
        flags = f[3] if len(f) > 3 else ""
        ov = {}
        if len(f) > 4 and f[4].strip():
            for kv in f[4].split(";"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    ov[k.strip()] = v.strip()
        if "x" in flags:
            continue
        r = prep.get(n)
        if r is None or not r.get("ndl"):
            problems.append(f"n={n} prep結果なし")
            continue
        nd = r["ndl"]

        title = ov.get("title") or r["title"]
        kana = re.sub(r"[:：].*$", "", ov.get("kana") or r.get("titleKana", ""))
        wid = ov.get("id") or uniq_id(r.get("workId", "").split(":")[0][:48].strip("-"), work_ids)

        # 海外作品(フラグ v)は責任表示から訳者を切り出す。「○○著 ; △△訳」の形が基本
        resp = (nd.get("resp") or "")
        tr_names = []
        if ov.get("translator"):
            tr_names = [x.strip() for x in ov["translator"].split(",") if x.strip()]
        elif "v" in flags:
            for seg in re.split(r"[;；,、]", resp):
                seg = seg.strip()
                m = re.match(r"^(.+?)\s*(?:訳|共訳|翻訳)$", seg)
                if m:
                    nm = re.sub(r"[\s　]+", "", m.group(1))
                    nm = re.sub(r"[\[\]]", "", nm)
                    if nm and nm not in tr_names:
                        tr_names.append(nm)
        a_names = [x.strip() for x in ov["author"].split(",")] if ov.get("author") else [r["author"]]
        persons = {p["name"]: p for p in r.get("persons", [])}
        author_ids = []
        for nm in a_names:
            key = norm(re.sub(r"（.*?）", "", nm))
            if key in author_by_name:
                author_ids.append(author_by_name[key])
                continue
            k = (persons.get(nm) or {}).get("kana", "") or kana_lookup(nm, kana_cache)
            base = romaji(k) if k else ""
            if not re.fullmatch(r"[a-z0-9\-]+", base or ""):
                base = "author-" + str(abs(hash(nm)) % 10 ** 6)
            pid = uniq_id(base, author_ids_taken)
            new_authors.append({"id": pid, "name": nm, "nameKana": k or nm,
                                "description": "ミステリ作品を手がける小説家。",
                                "externalLinks": {},
                                "sourceNote": f"国立国会図書館サーチの書誌で確認({TODAY})。",
                                "updatedAt": TODAY})
            author_by_name[key] = pid
            author_ids.append(pid)

        translator_ids = []
        for nm in tr_names:
            key = norm(nm)
            if key in translator_by_name:
                translator_ids.append(translator_by_name[key])
                continue
            k = kana_lookup(nm, kana_cache)
            base = romaji(k) if k else ""
            if not re.fullmatch(r"[a-z0-9\-]+", base or ""):
                base = "tr-" + str(abs(hash(nm)) % 10 ** 6)
            pid = uniq_id(base + ("-tr" if base in translator_ids_taken else ""), translator_ids_taken)
            new_translators.append({"id": pid, "name": nm, "nameKana": k or nm,
                                    "description": "翻訳者。",
                                    "externalLinks": {},
                                    "sourceNote": f"国立国会図書館サーチの責任表示で確認({TODAY})。",
                                    "updatedAt": TODAY})
            translator_by_name[key] = pid
            translator_ids.append(pid)

        pub_id = ov.get("pub", "")
        if not pub_id:
            pub_id = pub_by_name.get(norm(re.sub(r"\s*[（(].*$", "", nd.get("publisher", "") or "")), "")
        if not pub_id:
            problems.append(f"n={n} {title}: 出版社未解決 (NDL='{nd.get('publisher')}')")
            continue

        themes_l = [t.strip() for t in theme_str.split(",") if t.strip()]
        bad = [t for t in themes_l if t not in theme_ids]
        if bad:
            problems.append(f"n={n} {title}: 未知のテーマid {bad}")
            continue

        award_id = ov.get("award") or r.get("awardId", "")
        ayear = int(ov.get("ayear") or r.get("year") or 0)
        year = int(ov.get("year") or nd.get("firstYear") or ayear or 0) or None
        # NDLの最古刊行年は同名異作や文庫版を巻き込んで外すことがある(CLAUDE.md参照)。
        # 新人賞の受賞作は受賞年に刊行されるので、受賞年から大きく離れていたら受賞年を採る
        if ayear and year and not (ayear - 1 <= year <= ayear + 2):
            year = ayear
        result = ov.get("result") or r.get("prize") or "受賞"

        overseas = "v" in flags
        if overseas and (not translator_ids or not (ov.get("otitle") or nd.get("originalTitle"))):
            problems.append(f"n={n} {title}: 海外作品だが訳者または原題が取れない (resp='{resp}')")
            continue
        w = {
            "id": wid, "title": title, "titleKana": kana,
            "authorIds": author_ids, "translatorIds": translator_ids,
            "publisherId": pub_id, "themeIds": themes_l,
            "origin": "overseas" if overseas else "jp",
            "firstPublishedYear": year,
            "status": "ongoing" if "o" in flags else "completed",
            "synopsis": synopsis,
            "awardResults": ([{"awardId": award_id, "year": ayear, "result": result}]
                             if award_id and ayear else []),
            "mediaMix": {"movie": "m" in flags, "drama": "d" in flags,
                         "anime": "a" in flags, "comic": "c" in flags},
            "externalLinks": {},
            "sourceNote": SOURCE_NOTE.format(award=award_name, date=TODAY)
            + ("あらすじの典拠が見つからなかったため、内容の記述は書誌事項から確認できる範囲にとどめている。"
               if "n" in flags else ""),
            "updatedAt": TODAY,
        }
        if overseas:
            w["originalTitle"] = ov.get("otitle") or nd.get("originalTitle")
            w["jpPublishedYear"] = int(ov.get("jpyear") or nd.get("firstYear") or ayear or 0) or None
            w["firstPublishedYear"] = int(ov.get("year") or r.get("originalYear")
                                          or w["jpPublishedYear"] or 0) or None
        if ov.get("series"):
            w["seriesName"] = ov["series"]
        out_works.append(w)

    kana_cache_path.write_text(json.dumps(kana_cache, ensure_ascii=False), encoding="utf-8")
    batch = {"newAuthors": new_authors, "newTranslators": new_translators,
             "newPublishers": [], "newThemes": [], "newAwards": [], "works": out_works}
    Path(out_path).write_text(json.dumps(batch, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"works={len(out_works)} newAuthors={len(new_authors)} newTranslators={len(new_translators)}")
    for p in problems:
        print("! " + p)


if __name__ == "__main__":
    main()
