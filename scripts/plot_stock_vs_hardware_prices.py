"""Compare stock-news pressure, equity prices, and retail hardware prices by month."""

import csv
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MONTHS = ["2026-06", "2026-07", "2026-08", "2026-09"]
OUTPUT = ROOT / "output/stock_news_vs_ram_gpu_prices_2026-07_to_09.svg"
TABLE = ROOT / "output/stock_news_vs_ram_gpu_prices_2026-07_to_09.csv"


def line(points, color, width=3):
    coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>'


def main():
    data = json.loads((ROOT / "dataset/chin/prices/retail-and-cloud-price-contract.json").read_text())
    retail = {"DDR5 retail": data["ram"]["ddr5"], "DDR4 retail": data["ram"]["ddr4"],
              "Consumer GPU retail": data["gpuRetail"]}
    retail = {name: {r["month"]: float(r["index"]) for r in rows if r["month"] in MONTHS}
              for name, rows in retail.items()}

    price_file = ROOT / "dataset/ram_gpu_stocks/data/processed/stock_prices_2025-01-01_2026-09-30.csv"
    stock = defaultdict(dict)
    with price_file.open(newline="") as stream:
        for row in csv.DictReader(stream):
            month = row["date"][:7]
            if month in MONTHS:
                stock[row["ticker"]][month] = float(row["close"])

    pressures = defaultdict(list)
    report = ROOT / "output/stock_news_jev_5day_backtest_2026-07_to_09.csv"
    with report.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row["status"] == "SCORED":
                pressures[(row["ticker"], row["start_date"][:7])].append(float(row["pressure_score"]))

    table_rows = []
    for month in MONTHS:
        row = {"month": month}
        for name, values in retail.items():
            row[name + " rebase"] = round(values[month] / values[MONTHS[0]] * 100, 2)
        for ticker in ("AMD", "MU", "NVDA"):
            row[ticker + " rebase"] = round(stock[ticker][month] / stock[ticker][MONTHS[0]] * 100, 2)
            scores = pressures[(ticker, month)]
            row[ticker + " mean pressure"] = round(sum(scores)/len(scores), 4) if scores else ""
            row[ticker + " scored days"] = len(scores)
        table_rows.append(row)
    with TABLE.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(table_rows[0]))
        writer.writeheader()
        writer.writerows(table_rows)

    width, height = 1200, 970
    x_positions = [195, 485, 775, 1065]
    panels = [(125, 330, 92, 121, "Retail hardware price index"),
              (415, 620, 65, 115, "Stock closing price"),
              (710, 870, -0.04, 0.13, "Mean Jev stock-news pressure")]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#263445}.title{font-size:28px;font-weight:bold}.sub{font-size:16px;fill:#607080}.label{font-size:18px;font-weight:bold}.tick{font-size:13px;fill:#607080}</style>',
             '<text x="50" y="47" class="title">Stock news alongside RAM and consumer GPU prices</text>',
             '<text x="50" y="76" class="sub">July–September 2026 · price series rebased to June = 100 · news pressure shown in rubric units</text>']
    def yy(value, panel):
        top, bottom, low, high, _ = panel
        return bottom - (value-low)/(high-low)*(bottom-top)
    for panel in panels:
        top, bottom, low, high, title = panel
        parts.append(f'<text x="50" y="{top-22}" class="label">{title}</text>')
        for tick in ([95,100,105,110,115,120] if top==125 else
                     [70,80,90,100,110] if top==415 else [-0.04,0,0.04,0.08,0.12]):
            y=yy(tick,panel)
            if top <= y <= bottom:
                stroke = "#9ba7b2" if tick in (0,100) else "#e9edf0"
                parts.append(f'<line x1="{x_positions[0]}" y1="{y:.1f}" x2="{x_positions[-1]}" y2="{y:.1f}" stroke="{stroke}"/>')
                parts.append(f'<text x="{x_positions[0]-15}" y="{y+4:.1f}" text-anchor="end" class="tick">{tick:g}</text>')
        for x, month in zip(x_positions, MONTHS):
            parts.append(f'<text x="{x}" y="{bottom+25}" text-anchor="middle" class="tick">{month}</text>')

    hardware_colors = {"DDR5 retail": "#9452ad", "DDR4 retail": "#42a076", "Consumer GPU retail": "#d4783d"}
    stock_colors = {"AMD": "#d45a4c", "MU": "#7d5bc8", "NVDA": "#2b89ab"}
    for name,color in hardware_colors.items():
        points=[(x_positions[i], yy(table_rows[i][name+" rebase"], panels[0])) for i in range(4)]
        parts.append(line(points,color))
        for x,y in points:parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}"/>')
    for ticker,color in stock_colors.items():
        points=[(x_positions[i], yy(table_rows[i][ticker+" rebase"], panels[1])) for i in range(4)]
        parts.append(line(points,color))
        for x,y in points:parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}"/>')
        points=[(x_positions[i], yy(table_rows[i][ticker+" mean pressure"], panels[2]))
                for i in range(1,4) if table_rows[i][ticker+" mean pressure"] != ""]
        parts.append(line(points,color))
        for x,y in points:parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}"/>')
    for x,color,label in [(55,"#9452ad","DDR5 retail"),(260,"#42a076","DDR4 retail"),
                          (450,"#d4783d","Consumer GPU retail"),(735,"#d45a4c","AMD stock"),
                          (930,"#7d5bc8","MU stock"),(1060,"#2b89ab","NVDA stock")]:
        parts.append(f'<line x1="{x}" y1="915" x2="{x+22}" y2="915" stroke="{color}" stroke-width="4"/>')
        parts.append(f'<text x="{x+29}" y="920" class="tick">{label}</text>')
    parts.append('<text x="50" y="953" class="tick">Retail prices are monthly snapshots; stocks are last trading-day closes. Mean pressure uses scored stock-news cases; these are different targets and units.</text>')
    parts.append('</svg>')
    OUTPUT.write_text("\n".join(parts))
    print(OUTPUT)
    print(TABLE)


if __name__ == "__main__":
    main()
