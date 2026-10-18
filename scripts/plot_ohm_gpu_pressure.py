"""Compare continuous article pressure with observed GPU retail-price changes."""

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "output/ohm_gpu_price_pressure_2024-05_to_2026-10.csv"
OUTPUT = ROOT / "output/ohm_gpu_price_pressure_vs_actual.svg"


def main() -> None:
    with SOURCE.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    width, height = 1580, 750
    left, right = 160, 45
    step = (width-left-right)/len(rows)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#213347}.title{font-size:28px;font-weight:bold}.sub{font-size:16px;fill:#607082}.label{font-size:17px;font-weight:bold}.tick{font-size:12px;fill:#607082}</style>',
             '<text x="45" y="49" class="title">GPU article price pressure vs observed retail-price change</text>',
             '<text x="45" y="78" class="sub">Pressure is a signed rubric score, not a forecast in percent. Missing articles are left blank, not set to zero.</text>',
             '<text x="45" y="156" class="label">Article pressure</text>',
             '<text x="45" y="180" class="sub">rubric units</text>',
             '<text x="45" y="410" class="label">Actual price</text>',
             '<text x="45" y="434" class="sub">change (%)</text>']
    pressure_zero, pressure_scale = 262, 150
    actual_zero, actual_scale = 535, 19
    for zero, ticks, scale in ((pressure_zero, [-1, 0, 0.5, 1], pressure_scale),
                               (actual_zero, [-6, -4, -2, 0, 2, 4, 6, 8], actual_scale)):
        for tick in ticks:
            y = zero-tick*scale
            parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="#{"8b9aaa" if tick == 0 else "e9edf0"}"/>')
            parts.append(f'<text x="{left-12}" y="{y+4:.1f}" text-anchor="end" class="tick">{tick:g}</text>')
    for i,row in enumerate(rows):
        x = left+i*step+step/2
        month = row["case_month"]
        parts.append(f'<text x="{x:.1f}" y="657" transform="rotate(-55 {x:.1f} 657)" class="tick">{month}</text>')
        if row["actual_change_pct"]:
            change = float(row["actual_change_pct"])
            y = actual_zero-change*actual_scale
            color = "#267f63" if change >= 0 else "#c75157"
            parts.append(f'<rect x="{x-11:.1f}" y="{min(y,actual_zero):.1f}" width="22" height="{max(abs(y-actual_zero),1):.1f}" fill="{color}" opacity=".83"/>')
        if row["price_pressure_score"]:
            pressure = float(row["price_pressure_score"])
            y = pressure_zero-pressure*pressure_scale
            parts.append(f'<line x1="{x:.1f}" y1="{pressure_zero}" x2="{x:.1f}" y2="{y:.1f}" stroke="#d59227" stroke-width="3"/>')
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="#e6a52e" stroke="white" stroke-width="2"/>')
            parts.append(f'<text x="{x:.1f}" y="{y-13:.1f}" text-anchor="middle" class="tick">{pressure:+.2f}</text>')
    parts.append('<text x="45" y="710" class="sub">Gold: article pressure · Green/red: observed next-month retail-index change · Blank pressure: no stored Jev judgment.</text>')
    parts.append('<text x="45" y="735" class="tick">Source: OHM GPU news_feed.csv, cached article judgments, consumer GPU retail index. Scores have not been calibrated to price returns.</text>')
    parts.append('</svg>')
    OUTPUT.write_text("\n".join(parts))
    print(OUTPUT)


if __name__ == "__main__":
    main()
