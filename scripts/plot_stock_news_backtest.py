"""Render the three-month stock-news pressure backtest as SVG."""

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "output/stock_news_jev_5day_backtest_2026-07_to_09.csv"
DEST = ROOT / "output/stock_news_jev_5day_pressure_vs_return.svg"


def main():
    rows = [r for r in csv.DictReader(SOURCE.open())
            if r["status"] == "SCORED" and r["outcome_status"] == "OBSERVED"]
    width, height = 1100, 730
    left, right, top, bottom = 110, 55, 125, 585
    xmin, xmax, ymin, ymax = -0.15, 0.55, -30.0, 30.0
    sx = lambda v: left + (v-xmin)/(xmax-xmin)*(width-left-right)
    sy = lambda v: bottom - (v-ymin)/(ymax-ymin)*(bottom-top)
    colors = {"AMD": "#d86b43", "MU": "#7155b7", "NVDA": "#258f90"}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#243345}.title{font-size:27px;font-weight:bold}.sub{font-size:16px;fill:#5d6d7e}.axis{font-size:14px;fill:#5d6d7e}</style>',
             '<text x="42" y="46" class="title">Stock-news pressure vs following 5-session return</text>',
             '<text x="42" y="76" class="sub">July–September 2026 · 124 scored cases with observed outcomes · Jev rubric score is not a return forecast</text>']
    for x in (-0.1, 0, 0.1, 0.2, 0.3, 0.4, 0.5):
        xx=sx(x)
        parts.append(f'<line x1="{xx:.1f}" y1="{top}" x2="{xx:.1f}" y2="{bottom}" stroke="#{"8998a8" if x == 0 else "e8edf1"}"/>')
        parts.append(f'<text x="{xx:.1f}" y="{bottom+23}" text-anchor="middle" class="axis">{x:+g}</text>')
    for y in (-30,-20,-10,0,10,20,30):
        yy=sy(y)
        parts.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{width-right}" y2="{yy:.1f}" stroke="#{"8998a8" if y == 0 else "e8edf1"}"/>')
        parts.append(f'<text x="{left-14}" y="{yy+5:.1f}" text-anchor="end" class="axis">{y:+g}%</text>')
    for row in rows:
        x,y=float(row["pressure_score"]),float(row["actual_5day_pct"])
        color=colors[row["ticker"]]
        parts.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="5.5" fill="{color}" fill-opacity=".63" stroke="white" stroke-width=".6"><title>{row["ticker"]} {row["start_date"]}: pressure {x:+.3f}, return {y:+.2f}%</title></circle>')
    parts.append(f'<text x="{(left+width-right)/2:.1f}" y="{bottom+58}" text-anchor="middle" class="axis">Signed article pressure score</text>')
    parts.append('<text x="25" y="380" transform="rotate(-90 25 380)" text-anchor="middle" class="axis">Following 5-session close-to-close return</text>')
    for x,ticker in ((340,"AMD"),(480,"MU"),(600,"NVDA")):
        parts.append(f'<circle cx="{x}" cy="676" r="7" fill="{colors[ticker]}"/><text x="{x+15}" y="682" class="axis">{ticker}</text>')
    parts.append('<text x="42" y="714" class="axis">105 nonzero-pressure cases: 48.6% sign agreement; always-up baseline on the same cases: 57.1%. Correlation: −0.18.</text>')
    parts.append('</svg>')
    DEST.write_text("\n".join(parts))
    print(DEST)


if __name__ == "__main__":
    main()
