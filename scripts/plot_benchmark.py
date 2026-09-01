"""Render publication-style SVG figures from a benchmark derived-scores CSV.

Dependency-free (standard library only) and deterministic: the same CSV always produces byte-identical
SVGs, so the figures can be regenerated and diffed in CI. It reads ONLY the public derived-scores CSV
(aggregate 1-5 human scores), never any corpus, translation, or generated prose.

Usage:
    python scripts/plot_benchmark.py \
        --scores benchmarks/lotm/results/lotm-opus48-v1_ch00001-ch00006_scores.csv \
        --out-dir benchmarks/lotm/results/assets

Produces:
    dimension_means.svg      mean A/B/C score per evaluation dimension, informative chapters only.
    ctx_term_progression.svg contextual-correctness and terminology-consistency across chapters.

The score axis is fixed to 1-5. No confidence intervals, radar, or pie charts: these are ordinal
human scores from a single small run, and the figures are deliberately plain.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

# Condition colours (stable, colour-blind-friendly, legible on white). Order is fixed A, B, C.
COLORS = {"A": "#4e79a7", "B": "#f28e2b", "C": "#59a14f"}
CONDS = ["A", "B", "C"]
COND_LABEL = {
    "A": "A  chapter-only",
    "B": "B  rolling context",
    "C": "C  Wenmai memory",
}

# Dimensions shown in the means figure, with compact axis labels. Both annotation dimensions are
# omitted on purpose: the evaluator scored them on only a subset of chapters (annotation_precision on
# very few; annotation_restraint on fewer chapters than the literary dimensions, with unequal Ns
# across conditions), so their means are not comparable to the nine-chapter literary means shown here.
# They are reported separately, with explicit Ns, in the results write-up instead.
DIMENSIONS = [
    ("faithfulness", "Faithfulness"),
    ("contextual_correctness", "Contextual"),
    ("terminology_consistency", "Terminology"),
    ("character_voice_consistency", "Char. voice"),
    ("english_prose_quality", "Prose"),
    ("wordplay_preservation", "Wordplay"),
    ("hallucination_or_embellishment", "Hallucination"),
]

INK = "#222222"      # text
AXIS = "#666666"     # axis lines / ticks
GRID = "#e6e6e6"     # gridlines
BG = "#ffffff"       # figure background (keeps the figure legible in light and dark READMEs)

Y_MIN, Y_MAX = 1, 5  # fixed score axis


def _read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _num(value):
    return float(value) if value not in ("", None) else None


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _info_chapters(rows: list[dict]) -> list[int]:
    """Sorted, unique informative chapter numbers present in the CSV (drives ranges dynamically)."""
    return sorted({int(r["chapter"]) for r in rows if r["informative"] == "True"})


def _fmt(value: float) -> str:
    """Trim trailing zeros so 4.40 -> 4.4 and 5.00 -> 5 for compact labels."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _svg_open(w: int, h: int) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="Helvetica, Arial, sans-serif">',
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="{BG}"/>',
    ]


def _y_for(score: float, top: float, plot_h: float) -> float:
    return top + (Y_MAX - score) / (Y_MAX - Y_MIN) * plot_h


def _legend(cx: float, cy: float) -> list[str]:
    out, x = [], cx
    for cond in CONDS:
        out.append(f'<rect x="{x:.1f}" y="{cy - 9:.1f}" width="11" height="11" '
                   f'fill="{COLORS[cond]}"/>')
        out.append(f'<text x="{x + 16:.1f}" y="{cy:.1f}" font-size="12" fill="{INK}">'
                   f'{COND_LABEL[cond]}</text>')
        x += 150
    return out


def dimension_means_svg(rows: list[dict]) -> str:
    info = [r for r in rows if r["informative"] == "True"]
    # mean per (dimension, condition) over informative chapters
    means = {}
    for key, _ in DIMENSIONS:
        for cond in CONDS:
            vals = [_num(r[key]) for r in info if r["condition"] == cond]
            means[(key, cond)] = _mean(vals)

    W, H = 760, 400
    left, right, top, bottom = 46, 16, 54, 96
    plot_w = W - left - right
    plot_h = H - top - bottom
    baseline = top + plot_h

    chs = _info_chapters(rows)
    span = f"{chs[0]}-{chs[-1]}" if chs else ""

    s = _svg_open(W, H)
    s.append(f'<text x="{left}" y="26" font-size="15" font-weight="bold" fill="{INK}">'
             f'Mean human score by dimension (informative chapters {span})</text>')
    s += _legend(left, 44)

    # gridlines + y labels at each integer 1..5
    for g in range(Y_MIN, Y_MAX + 1):
        y = _y_for(g, top, plot_h)
        s.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" '
                 f'stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{left - 8}" y="{y + 4:.1f}" font-size="11" fill="{AXIS}" '
                 f'text-anchor="end">{g}</text>')
    s.append(f'<line x1="{left}" y1="{top:.1f}" x2="{left}" y2="{baseline:.1f}" '
             f'stroke="{AXIS}" stroke-width="1"/>')
    s.append(f'<line x1="{left}" y1="{baseline:.1f}" x2="{left + plot_w}" y2="{baseline:.1f}" '
             f'stroke="{AXIS}" stroke-width="1"/>')

    n = len(DIMENSIONS)
    group_w = plot_w / n
    bar_w = group_w / (len(CONDS) + 1.6)
    for i, (key, label) in enumerate(DIMENSIONS):
        gx = left + i * group_w
        for j, cond in enumerate(CONDS):
            v = means[(key, cond)]
            if v is None:
                continue
            bx = gx + group_w / 2 - (len(CONDS) * bar_w) / 2 + j * bar_w
            by = _y_for(v, top, plot_h)
            s.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w - 2:.1f}" '
                     f'height="{baseline - by:.1f}" fill="{COLORS[cond]}"/>')
            s.append(f'<text x="{bx + (bar_w - 2) / 2:.1f}" y="{by - 3:.1f}" font-size="9.5" '
                     f'fill="{AXIS}" text-anchor="middle">{_fmt(v)}</text>')
        s.append(f'<text x="{gx + group_w / 2:.1f}" y="{baseline + 16:.1f}" font-size="11" '
                 f'fill="{INK}" text-anchor="middle">{label}</text>')

    s.append(f'<text x="{left}" y="{H - 8}" font-size="10" fill="{AXIS}">'
             f'Score 1-5 (5 = best); means exclude null observations. The two annotation dimensions '
             f'are omitted here (scored on fewer chapters, unequal Ns) and reported in the write-up.'
             f'</text>')
    s.append("</svg>")
    return "\n".join(s) + "\n"


def _progression_panel(rows, key, panel_x, panel_y, panel_w, panel_h, title):
    chapters = _info_chapters(rows)
    top, bottom = panel_y + 26, panel_y + panel_h - 24
    left = panel_x + 26
    right = panel_x + panel_w - 8
    plot_h = bottom - top
    plot_w = right - left
    out = [f'<text x="{panel_x + panel_w / 2:.1f}" y="{panel_y + 14:.1f}" font-size="12.5" '
           f'font-weight="bold" fill="{INK}" text-anchor="middle">{title}</text>']

    for g in range(Y_MIN, Y_MAX + 1):
        y = top + (Y_MAX - g) / (Y_MAX - Y_MIN) * plot_h
        out.append(f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" '
                   f'stroke="{GRID}" stroke-width="1"/>')
        out.append(f'<text x="{left - 6}" y="{y + 4:.1f}" font-size="10" fill="{AXIS}" '
                   f'text-anchor="end">{g}</text>')
    out.append(f'<line x1="{left}" y1="{top:.1f}" x2="{left}" y2="{bottom:.1f}" '
               f'stroke="{AXIS}" stroke-width="1"/>')
    out.append(f'<line x1="{left}" y1="{bottom:.1f}" x2="{right}" y2="{bottom:.1f}" '
               f'stroke="{AXIS}" stroke-width="1"/>')

    def px(ci):
        return left + (plot_w) * ci / (len(chapters) - 1)

    def py(v):
        return top + (Y_MAX - v) / (Y_MAX - Y_MIN) * plot_h

    for ci, ch in enumerate(chapters):
        out.append(f'<text x="{px(ci):.1f}" y="{bottom + 16:.1f}" font-size="10" fill="{INK}" '
                   f'text-anchor="middle">{ch}</text>')

    for cond in CONDS:
        pts = []
        for ci, ch in enumerate(chapters):
            row = next(r for r in rows if int(r["chapter"]) == ch and r["condition"] == cond)
            pts.append((px(ci), py(_num(row[key]))))
        path = " ".join(f'{"M" if i == 0 else "L"}{x:.1f} {y:.1f}' for i, (x, y) in enumerate(pts))
        out.append(f'<path d="{path}" fill="none" stroke="{COLORS[cond]}" stroke-width="2.2"/>')
        for x, y in pts:
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{COLORS[cond]}"/>')
    return out


def progression_svg(rows: list[dict]) -> str:
    W, H = 760, 340
    s = _svg_open(W, H)
    s.append(f'<text x="24" y="24" font-size="15" font-weight="bold" fill="{INK}">'
             f'Where the conditions converge, and where they do not</text>')
    s += _legend(24, 44)
    s += _progression_panel(rows, "contextual_correctness", 12, 58, 366, 262,
                            "Contextual correctness")
    s += _progression_panel(rows, "terminology_consistency", 384, 58, 366, 262,
                            "Terminology consistency")
    chs = _info_chapters(rows)
    span = f"{chs[0]}-{chs[-1]}" if chs else ""
    s.append(f'<text x="24" y="{H - 8}" font-size="10" fill="{AXIS}">'
             f'Score 1-5 by chapter (x), informative chapters {span}. Contextual correctness rises '
             f'toward 5 but separates again (e.g. ch7); terminology stays persistently separated.</text>')
    s.append("</svg>")
    return "\n".join(s) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Render benchmark SVG figures from a derived-scores CSV.")
    ap.add_argument("--scores", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--prefix", default="",
                    help="filename prefix for the SVGs (e.g. a run/chapter tag). Pass a prefix to "
                         "write checkpoint-specific names and avoid clobbering an earlier "
                         "checkpoint's committed assets. When omitted, the generic "
                         "'dimension_means.svg' / 'ctx_term_progression.svg' names are written, "
                         "overwriting any existing generic assets in the output dir.")
    args = ap.parse_args()

    rows = _read_rows(Path(args.scores))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pre = f"{args.prefix}_" if args.prefix else ""
    means_path = out_dir / f"{pre}dimension_means.svg"
    prog_path = out_dir / f"{pre}ctx_term_progression.svg"
    means_path.write_text(dimension_means_svg(rows), encoding="utf-8")
    prog_path.write_text(progression_svg(rows), encoding="utf-8")
    print(f"[plot] wrote {means_path}")
    print(f"[plot] wrote {prog_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
