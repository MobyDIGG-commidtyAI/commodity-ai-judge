"""Plot monthly RAM article pressure and next-month DDR5 changes on ±100% axes."""

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "output/ram_full_article_pressure_2024-10_to_2026-08_monthly.csv"
OUTPUT = ROOT / "output/ram_full_article_pressure_2024-10_to_2026-08_signed_100.svg"


def main():
    with SOURCE.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    width, height = 2200, 950
    left, right = 130, 80
    plot_width = width - left - right
    step = plot_width / len(rows)
    centers = [left + (i + 0.5) * step for i in range(len(rows))]
    panels = [(170, 410), (500, 740)]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="#ffffff"/>',
             '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#213247}.title{font-size:29px;font-weight:bold}.subtitle{font-size:17px;fill:#52657a}.panel{font-size:21px;font-weight:bold}.axis{font-size:14px;fill:#52657a}.value{font-size:15px;font-weight:bold}</style>',
             '<text x="50" y="52" class="title">RAM news pressure vs following-month DDR5 retail price change</text>',
             '<text x="50" y="84" class="subtitle">Two-year price window: Oct 2024–Sep 2026. News starts Jan 2025; unavailable months are shaded.</text>',
             '<text x="50" y="138" class="panel">Article pressure: (up articles − down articles) / saved articles</text>',
             '<text x="50" y="468" class="panel">Following-month DDR5 retail price change</text>']

    for top, bottom in panels:
        mid = (top + bottom) / 2
        for tick in (-100, -50, 0, 50, 100):
            y = mid - tick / 100 * (bottom - top) / 2
            stroke = '#8292a0' if tick == 0 else '#e3e9ef'
            sw = 1.8 if tick == 0 else 1
            parts.append(f'<line x1="{left}" x2="{width-right}" y1="{y:.1f}" y2="{y:.1f}" stroke="{stroke}" stroke-width="{sw}"/>')
            parts.append(f'<text x="{left-14}" y="{y+5:.1f}" text-anchor="end" class="axis">{tick:+d}%</text>')

    for i, (x, row) in enumerate(zip(centers, rows)):
        n = int(row['saved_full_articles'])
        pressure = 100 * (int(row['up']) - int(row['down'])) / n if n else None
        price = float(row['next_month_ddr5_change_pct'])
        for panel, val, color in ((panels[0], pressure, '#aa5144'), (panels[1], price, '#3f76a3')):
            top, bottom = panel
            mid = (top + bottom) / 2
            if val is None:
                parts.append(f'<rect x="{x-step*.45:.1f}" y="{top}" width="{step*.9:.1f}" height="{bottom-top}" fill="#f0f2f4"/>')
                continue
            y = mid - val / 100 * (bottom-top) / 2
            parts.append(f'<rect x="{x-16:.1f}" y="{min(y,mid):.1f}" width="32" height="{max(abs(y-mid),1):.1f}" fill="{color}" rx="2"/>')
            if abs(val) >= 10 or (panel == panels[1] and abs(val) >= 20):
                offset = -9 if val >= 0 else 19
                parts.append(f'<text x="{x:.1f}" y="{y+offset:.1f}" text-anchor="middle" class="value" fill="{color}">{val:+.0f}%</text>')
        month = row['news_month']
        parts.append(f'<text x="{x:.1f}" y="775" text-anchor="middle" class="axis">{month[5:]}</text>')
        if month.endswith('-01'):
            parts.append(f'<text x="{x:.1f}" y="810" text-anchor="middle" class="panel">{month[:4]}</text>')
            if i:
                sep = x - step/2
                parts.append(f'<line x1="{sep:.1f}" x2="{sep:.1f}" y1="170" y2="740" stroke="#b8c5cf" stroke-dasharray="5 5"/>')

    parts += ['<text x="50" y="860" class="subtitle">Red = net article pressure; blue = DDR5 price change one month later. Both panels use the same −100% to +100% scale.</text>',
              '<text x="50" y="889" class="subtitle">News values are based on saved MU articles with rule-matched RAM price sentences; they are descriptive, not validated predictions.</text>',
              '</svg>']
    OUTPUT.write_text('\n'.join(parts))
    print(OUTPUT)


if __name__ == '__main__':
    main()
