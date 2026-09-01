"""Build the pre-reference quantitative comparison universe for a benchmark reference analysis.

Source-driven ONLY. Reads the frozen Chinese source chapters plus the frozen human-reviewed canonical
state (characters, terminology, locations, factions) and translation memory under `.local/`. It NEVER
opens or consults the official English reference: the reference must not be used to decide which items
enter the quantitative sample. Timeline events are excluded on purpose (they are narrative beats, not
recurring translated lexical items).

Inclusion rule (both conditions required):
  1. the item is represented in the frozen reviewed canonical terminology / entity / location /
     faction / name state, or in the frozen translation memory; AND
  2. its source identity has >= 2 genuine occurrence opportunities across the source chapters.

Chinese-script aliases that the canonical state already groups under one entity are grouped for
counting; non-Chinese (Latin-script) aliases are display-only and are not counted against the source
text. `occurrence_count` is the total literal (non-overlapping) count of any grouped source key across
the frozen source chapters (`str.count`). One-off items (< 2) are excluded from the universe.

Deterministic: the same frozen inputs always produce a byte-identical CSV, so the inventory's
SHA-256 can be pre-registered in a public manifest before the reference is opened.

Usage:
    python scripts/build_reference_inventory.py \
        --state .local/benchmarks/lotm/state \
        --out   .local/benchmarks/lotm/reference_analysis/pre_reference_inventory.csv \
        --chapters 10
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

import yaml

CJK = re.compile(r"[㐀-鿿]")
CAT_ORDER = {"character": 0, "faction": 1, "location": 2, "terminology": 3, "tm_phrase": 4}
FIELDS = ["item_id", "category", "source_key", "keys_grouped", "english", "first_seen",
          "occurrence_count", "occurrence_chapters"]


def is_cjk(s: str) -> bool:
    return bool(s) and bool(CJK.search(s))


def _grouped_keys(keys) -> list[str]:
    out, seen = [], set()
    for k in keys:
        if is_cjk(k) and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def build(state_dir: Path, n_chapters: int) -> list[dict]:
    ctx = state_dir / "context"
    src = state_dir / "source"
    chapters = [f"ch{n:05d}" for n in range(1, n_chapters + 1)]
    src_text = {ch: (src / f"{ch}_zh.txt").read_text(encoding="utf-8") for ch in chapters}

    candidates: list[tuple] = []  # (category, source_key, keys, english, first_seen)

    def add(category, source_key, keys, english, first_seen):
        gk = _grouped_keys(keys)
        if gk:
            candidates.append((category, source_key, gk, english or "", first_seen or ""))

    chars = yaml.safe_load((ctx / "characters.yaml").read_text(encoding="utf-8"))["characters"]
    for c in chars:
        add("character", c.get("source"), [c.get("source")] + (c.get("aliases") or []),
            c.get("english"), c.get("first_seen"))

    terms = yaml.safe_load((ctx / "terminology.yaml").read_text(encoding="utf-8"))["terms"]
    for t in terms:
        add("terminology", t.get("source"), [t.get("source")], t.get("preferred"), t.get("first_seen"))

    locs = yaml.safe_load((ctx / "locations.yaml").read_text(encoding="utf-8"))["locations"]
    for l in locs:
        add("location", l.get("source"), [l.get("source")], l.get("english"), l.get("first_seen"))

    facs = yaml.safe_load((ctx / "factions.yaml").read_text(encoding="utf-8"))["factions"]
    for f in facs:
        add("faction", f.get("source"), [f.get("source")], f.get("english"), f.get("first_seen"))

    tm_path = state_dir / "translation_memory" / "phrases.jsonl"
    if tm_path.exists():
        for line in tm_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                gloss = (r.get("gloss") or "").split(":")[0].strip('"')
                add("tm_phrase", r.get("source"), [r.get("source")], gloss, r.get("first_seen"))

    rows = []
    for category, source_key, keys, english, first_seen in candidates:
        total, chs = 0, set()
        for ch in chapters:
            cnt = sum(src_text[ch].count(k) for k in keys)
            if cnt:
                total += cnt
                chs.add(ch)
        if total >= 2:
            rows.append({
                "item_id": "",
                "category": category,
                "source_key": source_key,
                "keys_grouped": "|".join(keys),
                "english": english,
                "first_seen": first_seen,
                "occurrence_count": total,
                "occurrence_chapters": ",".join(sorted(chs)),
            })

    rows.sort(key=lambda r: (CAT_ORDER[r["category"]], -r["occurrence_count"], r["source_key"]))
    for i, r in enumerate(rows, 1):
        r["item_id"] = f"item_{i:03d}"
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the pre-reference comparison universe CSV.")
    ap.add_argument("--state", required=True, help="benchmark state dir (contains context/, source/, translation_memory/)")
    ap.add_argument("--out", required=True, help="output CSV path (keep under .local/, it is source-derived)")
    ap.add_argument("--chapters", type=int, default=10)
    args = ap.parse_args()

    rows = build(Path(args.state), args.chapters)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    cc = Counter(r["category"] for r in rows)
    print(f"[inventory] included {len(rows)} items -> {out}")
    print(f"[inventory] category counts: {dict(sorted(cc.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
