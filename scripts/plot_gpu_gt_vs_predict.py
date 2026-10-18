"""Render the GPU article backtest as a standalone SVG without extra packages."""

import csv
import html
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "output/ohm_gpu_jev_article_backtest_2024-05_to_2026-10.csv"
DEST = ROOT / "output/ohm_gpu_gt_vs_predict_2024-05_to_2026-10.svg"


def main() -> None:
    with SOURCE.open(newline="") as stream:
        rows = list(csv.DictReader(stream))

    width, height = 1580, 780
    left, right = 165, 45
    step = (width - left - right) / len(rows)
    cell = step - 5
    colors = {"UP": "#18855a", "DOWN": "#d65454", "FLAT": "#e6ac35",
              "NO_ARTICLE": "#d9dfe5", "PENDING": "#f0f2f4"}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="#ffffff"/>',
             '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#243245} .title{font-size:29px;font-weight:bold} .sub{font-size:16px;fill:#586779} .axis{font-size:13px;fill:#586779} .label{font-size:17px;font-weight:bold}</style>',
             '<text x="55" y="54" class="title">Consumer GPU price: ground truth vs Jev prediction</text>',
             '<text x="55" y="82" class="sub">Monthly next-price direction · case months May 2024–Oct 2026 · target months Jun 2024–Nov 2026</text>',
             '<text x="55" y="151" class="label">Ground truth</text>',
             '<text x="55" y="224" class="label">Jev prediction</text>',
             '<text x="55" y="330" class="label">Actual monthly</text>',
             '<text x="55" y="353" class="label">change (%)</text>']

    for i, row in enumerate(rows):
        x = left + i * step
        gt = row["actual_direction"] if row["actual_direction"] in ("UP", "DOWN") else "PENDING"
        pred = row["prediction"] if row["prediction"] in colors else "PENDING"
        for y, value in ((123, gt), (196, pred)):
            parts.append(f'<rect x="{x:.1f}" y="{y}" width="{cell:.1f}" height="46" rx="5" fill="{colors[value]}"/>')
            if value == "FLAT":
                parts.append(f'<text x="{x + cell/2:.1f}" y="225" text-anchor="middle" font-size="12" font-weight="bold" fill="#ffffff">F</text>')
        label = html.escape(row["target_month"])
        parts.append(f'<text x="{x + cell/2:.1f}" y="264" transform="rotate(-55 {x + cell/2:.1f} 264)" class="axis">{label}</text>')

    top, bottom, zero, scale = 330, 615, 490, 20
    for tick in (-6, -4, -2, 0, 2, 4, 6, 8):
        y = zero - tick * scale
        if top <= y <= bottom:
            parts.append(f'<line x1="{left}" y1="{y}" x2="{width-right}" y2="{y}" stroke="#{"9aa8b7" if tick == 0 else "e9edf0"}" stroke-width="{1.5 if tick == 0 else 1}"/>')
            parts.append(f'<text x="{left-13}" y="{y+5}" text-anchor="end" class="axis">{tick:+d}</text>')
    for i, row in enumerate(rows):
        raw = row["actual_change_pct"]
        if not raw:
            continue
        value = float(raw)
        x = left + i * step + 5
        y = zero - value * scale
        bar_y = min(y, zero)
        bar_h = abs(y - zero)
        color = colors["UP" if value >= 0 else "DOWN"]
        parts.append(f'<rect x="{x:.1f}" y="{bar_y:.1f}" width="{max(cell-10, 2):.1f}" height="{max(bar_h,1):.1f}" fill="{color}" opacity=".82"/>')
        if row["prediction"] == "FLAT":
            parts.append(f'<circle cx="{x+(cell-10)/2:.1f}" cy="{y:.1f}" r="5" fill="#e6ac35" stroke="white" stroke-width="1.5"/>')

    legend = [("#18855a", "Actual UP"), ("#d65454", "Actual DOWN"),
              ("#e6ac35", "Jev FLAT (abstained)"), ("#d9dfe5", "No dated full article"),
              ("#f0f2f4", "Price pending")]
    x = 55
    for color, title in legend:
        parts.append(f'<rect x="{x}" y="664" width="17" height="17" rx="3" fill="{color}"/>')
        parts.append(f'<text x="{x+25}" y="678" class="axis">{html.escape(title)}</text>')
        x += 25 + len(title)*8.5 + 25
    parts.append('<text x="55" y="719" class="sub">5 judged months: all FLAT; 23 completed months lacked a dated full article. No directional predictions to score.</text>')
    parts.append('<text x="55" y="744" class="axis">Source: OHM GPU Jev article backtest CSV. September and October 2026 case months have pending target prices.</text>')
    parts.append('</svg>')
    DEST.write_text("\n".join(parts))
    print(DEST)


if __name__ == "__main__":
    main()
