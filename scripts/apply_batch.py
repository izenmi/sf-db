#!/usr/bin/env python3
"""汎用バッチ反映スクリプト。
使い方: python3 scripts/apply_batch.py <batch.json>

batch.json の形式:
{
  "newAuthors": [...],
  "newTranslators": [...],
  "newPublishers": [...],
  "newThemes": [...],
  "newAwards": [...],
  "works": [...]
}

- 新規id(author/translator/publisher/theme/award)は既存と重複していればスキップ
- work は authorIds/translatorIds/publisherId/themeIds/awardResults[].awardId が
  (既存 + このバッチで追加される新規id) の中に存在するか検証し、
  存在しない参照があればその work 自体を反映せずレポートする
- origin ごとの必須項目(海外作品なら translatorIds と originalTitle、国内作品ならそれらが
  空であること)も検証する。generate-manifest.mjs と同じルール
- 既存work idと重複するworkはスキップ
"""
import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "public" / "data" / "source"

def load(name):
    with open(SRC / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)

def save(name, data):
    with open(SRC / f"{name}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

def main():
    if len(sys.argv) != 2:
        print("usage: apply_batch.py <batch.json>")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        batch = json.load(f)

    authors = load("authors")
    translators = load("translators")
    publishers = load("publishers")
    themes = load("themes")
    awards = load("awards")
    works = load("works")

    author_ids = {a["id"] for a in authors}
    translator_ids = {t["id"] for t in translators}
    publisher_ids = {p["id"] for p in publishers}
    theme_ids = {t["id"] for t in themes}
    award_ids = {a["id"] for a in awards}
    work_ids = {w["id"] for w in works}

    report = {"added": {}, "skipped_duplicates": {}, "rejected_works": []}

    def add_new(pool, id_set, key_name, kind):
        added, skipped = [], []
        for item in batch.get(key_name, []):
            if item["id"] in id_set:
                skipped.append(item["id"])
            else:
                pool.append(item)
                id_set.add(item["id"])
                added.append(item["id"])
        report["added"][kind] = added
        report["skipped_duplicates"][kind] = skipped

    add_new(authors, author_ids, "newAuthors", "authors")
    add_new(translators, translator_ids, "newTranslators", "translators")
    add_new(publishers, publisher_ids, "newPublishers", "publishers")
    add_new(themes, theme_ids, "newThemes", "themes")
    add_new(awards, award_ids, "newAwards", "awards")

    added_works = []
    for w in batch.get("works", []):
        if w["id"] in work_ids:
            report["rejected_works"].append({"id": w["id"], "reason": "duplicate work id"})
            continue

        missing = []
        if not w.get("authorIds"):
            missing.append("authorIds is empty")
        for aid in w.get("authorIds", []):
            if aid not in author_ids:
                missing.append(f"authorId:{aid}")
        for tid in w.get("translatorIds", []):
            if tid not in translator_ids:
                missing.append(f"translatorId:{tid}")
        pid = w.get("publisherId")
        if pid and pid not in publisher_ids:
            missing.append(f"publisherId:{pid}")
        for tid in w.get("themeIds", []):
            if tid not in theme_ids:
                missing.append(f"themeId:{tid}")
        for ar in w.get("awardResults", []):
            if ar.get("awardId") not in award_ids:
                missing.append(f"awardId:{ar.get('awardId')}")

        origin = w.get("origin")
        if origin not in ("jp", "overseas"):
            missing.append(f"origin must be jp/overseas (got {origin!r})")
        elif origin == "overseas":
            if not w.get("translatorIds"):
                missing.append("overseas work needs at least one translator")
            if not w.get("originalTitle"):
                missing.append("overseas work needs originalTitle")
        else:
            if w.get("translatorIds"):
                missing.append("domestic work must not have translators")
            if w.get("originalTitle"):
                missing.append("domestic work must not have originalTitle")
            if w.get("jpPublishedYear"):
                missing.append("domestic work must not have jpPublishedYear")

        if missing:
            report["rejected_works"].append({"id": w["id"], "reason": f"invalid: {missing}"})
            continue

        works.append(w)
        work_ids.add(w["id"])
        added_works.append(w["id"])

    report["added"]["works"] = added_works

    save("authors", authors)
    save("translators", translators)
    save("publishers", publishers)
    save("themes", themes)
    save("awards", awards)
    save("works", works)

    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
