#!/usr/bin/env python3
"""既に登録済みの作品に受賞歴だけを追加する。受賞作パイプラインの「2段構え」の第1段。

  python3 scripts/add_awards.py rows.tsv

rows.tsv は1行1件、`workId<TAB>awardId<TAB>year<TAB>result`(区切りは TAB でも `|` でもよい)。

**なぜ要るか**: `apply_batch.py` は新規作品しか入れないので、賞のページを取り込むときに
「未登録の受賞作を追加する」ことだけをやると、**既に入っている作品の受賞歴が丸ごと落ちる**。
姉妹サイトで実際にこれをやって1149件の受賞歴を欠落させた事故があるため、
賞を1つ取り込むたびに (1) 既存作品へ付与 → (2) 未登録作品を追加、の順で必ず両方を回すこと。

同じ awardId・year・result の組がすでにあれば何もしない(何度流しても二重登録にならない)。
"""
import json
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "public" / "data" / "source" / "works.json"


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: add_awards.py <rows.tsv>")
    works = json.loads(SRC.read_text(encoding="utf-8"))
    by_id = {w["id"]: w for w in works}
    awards = {a["id"] for a in json.loads(
        (SRC.parent / "awards.json").read_text(encoding="utf-8"))}

    added, skipped, missing = 0, 0, []
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = re.split(r"\t|\|", line)
        if len(parts) < 4:
            missing.append(f"{line} (列が足りない)")
            continue
        wid, aid, year, result = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
        w = by_id.get(wid)
        if not w:
            missing.append(f"{wid} (works.jsonに無い)")
            continue
        if aid not in awards:
            missing.append(f"{wid} -> {aid} (awards.jsonに無い)")
            continue
        entries = w.setdefault("awardResults", [])
        if any(e["awardId"] == aid and e["year"] == int(year) and e["result"] == result for e in entries):
            skipped += 1
            continue
        entries.append({"awardId": aid, "year": int(year), "result": result})
        entries.sort(key=lambda e: (e["year"], e["awardId"]))
        added += 1

    SRC.write_text(json.dumps(works, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"追加 {added}件 / 既存でスキップ {skipped}件")
    if missing:
        print("-- 未反映 --")
        for m in missing:
            print(" ", m)


if __name__ == "__main__":
    main()
