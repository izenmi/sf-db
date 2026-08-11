#!/usr/bin/env python3
"""probe.json に出てくる人名・出版社が既存エンティティにあるかを一覧する。

使い方: python3 scripts/find_people.py <probe.json>
        python3 scripts/find_people.py --names 綾辻行人 有栖川有栖

著者104人・訳者58人・探偵67人の一覧をコンテキストに載せずに既存IDを引くための補助。
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "public" / "data" / "source"


def norm(s: str) -> str:
    return re.sub(r"[\s　・･,，.。]", "", unicodedata.normalize("NFKC", s or "")).lower()


def load(name):
    return {norm(x["name"]): x["id"] for x in json.loads((SRC / f"{name}.json").read_text(encoding="utf-8"))}


def main():
    authors, translators, publishers = load("authors"), load("translators"), load("publishers")
    if sys.argv[1:2] == ["--names"]:
        for nm in sys.argv[2:]:
            k = norm(nm)
            print(f"{nm}\ta={authors.get(k,'?')}\ttr={translators.get(k,'?')}")
        return
    for r in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")):
        if r.get("status") != "OK":
            continue
        au = r.get("author", "")
        print(f"{r['n']}\t{au}={authors.get(norm(au),'?')}\t"
              f"社:{r.get('publisher','')}={publishers.get(norm(r.get('publisher','')),'?')}")


if __name__ == "__main__":
    main()
