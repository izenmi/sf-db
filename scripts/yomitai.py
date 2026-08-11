#!/usr/bin/env python3
"""「SFが読みたい!」各年のベスト10(1999年〜)を年・部門・順位つきで抜き、未登録だけ出す。"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from award_wiki import fetch, norm

works = json.loads((Path(__file__).resolve().parent.parent / "public/data/source/works.json").read_text())
known = {norm(w["title"]) for w in works}

raw = fetch("SFが読みたい!")
raw = re.sub(r"\{\{small\|([^{}]*)\}\}", r" \1", raw)
raw = re.sub(r"\{\{仮リンク\|([^|}]+)(?:\|[^{}]*)?\}\}", r"\1", raw)
sec = raw[raw.find("=== 各年のベスト10 ==="):]
m_end = re.search(r"\n==[^=]", sec[5:])
if m_end:
    sec = sec[:5 + m_end.start()]

year = None
side = None
rank = 0
out = []
for line in sec.splitlines():
    m = re.match(r"====\s*(\d{4})年\s*====", line.strip())
    if m:
        year, side, rank = int(m.group(1)), None, 0
        continue
    if "国内篇" in line:
        side, rank = "国内篇", 0
        continue
    if "海外篇" in line:
        side, rank = "海外篇", 0
        continue
    if not line.startswith("#") or year is None or side is None:
        continue
    rank += 1
    body = line.lstrip("# ").strip()
    body = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", body)
    body = re.sub(r"\[\[([^\]]*)\]\]", r"\1", body)
    body = re.sub(r"<ref.*?</ref>", "", body, flags=re.S)
    body = re.sub(r"\{\{[^{}]*\}\}", "", body)
    body = re.sub(r"<[^>]+>", "", body)
    m2 = re.match(r"(.+)（([^（）]+)）\s*$", body)
    if not m2:
        continue
    title, author = m2.group(1).strip(), m2.group(2).strip()
    st = "DUP" if norm(title) in known else "new"
    out.append((st, year, side, rank, title, author))

for o in out:
    print("\t".join(str(x) for x in o))
print(f"-- new={sum(1 for o in out if o[0]=='new')} dup={sum(1 for o in out if o[0]=='DUP')}", file=sys.stderr)
