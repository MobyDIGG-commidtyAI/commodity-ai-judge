"""Align stock-news pressure with monthly stock and retail hardware deltas."""

import csv
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MONTHS = ["2026-07", "2026-08", "2026-09"]
PREVIOUS = ["2026-06", "2026-07", "2026-08"]
SVG = ROOT / "output/stock_pressure_vs_stock_ram_gpu_monthly_deltas_2026-07_to_09.svg"
CSV = ROOT / "output/stock_pressure_vs_stock_ram_gpu_monthly_deltas_2026-07_to_09.csv"


def main():
    data = json.loads((ROOT / "dataset/chin/prices/retail-and-cloud-price-contract.json").read_text())
    retail_sources = {"DDR4 retail": data["ram"]["ddr4"], "DDR5 retail": data["ram"]["ddr5"],
                      "Consumer GPU retail": data["gpuRetail"]}
    retail = {name: {item["month"]: float(item["index"]) for item in items}
              for name, items in retail_sources.items()}
    stock = defaultdict(dict)
    prices_path = ROOT / "dataset/ram_gpu_stocks/data/processed/stock_prices_2025-01-01_2026-09-30.csv"
    with prices_path.open(newline="") as stream:
        for item in csv.DictReader(stream):
            if item["date"][:7] in set(MONTHS + PREVIOUS):
                stock[item["ticker"]][item["date"][:7]] = float(item["close"])
    scores = defaultdict(list)
    report_path = ROOT / "output/stock_news_jev_5day_backtest_2026-07_to_09.csv"
    with report_path.open(newline="") as stream:
        for item in csv.DictReader(stream):
            if item["status"] == "SCORED":
                scores[(item["ticker"], item["start_date"][:7])].append(float(item["pressure_score"]))

    rows = []
    for month, previous in zip(MONTHS, PREVIOUS):
        row = {"month": month}
        for ticker in ("AMD", "MU", "NVDA"):
            row[f"{ticker}_mean_jev_pressure"] = round(sum(scores[(ticker, month)])/len(scores[(ticker, month)]), 4)
            row[f"{ticker}_scored_days"] = len(scores[(ticker, month)])
            row[f"{ticker}_stock_change_pct"] = round((stock[ticker][month]/stock[ticker][previous]-1)*100, 2)
        for name, values in retail.items():
            row[f"{name}_change_pct"] = round((values[month]/values[previous]-1)*100, 2)
        rows.append(row)
    with CSV.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    width, height = 1260, 820
    panels = [
        (145, 300, -0.04, 0.12, "Jev stock-news pressure", "rubric score"),
        (390, 555, -35, 35, "Stock closing-price delta", "% month over month"),
        (640, 760, -12, 15, "Retail hardware price delta", "% month over month"),
    ]
    x_groups = [260, 620, 980]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#263445}.title{font-size:28px;font-weight:bold}.sub{font-size:16px;fill:#5d6f80}.label{font-size:18px;font-weight:bold}.tick{font-size:13px;fill:#627283}.value{font-size:12px;font-weight:bold}</style>',
             '<text x="45" y="46" class="title">Jev stock-news pressure vs monthly price changes</text>',
             '<text x="45" y="75" class="sub">Same calendar months: July–September 2026 · pressure is a five-session stock score, not a percent forecast</text>']
    def y_pos(value, panel):
        top,bottom,minimum,maximum,_,_=panel
        return bottom-(value-minimum)/(maximum-minimum)*(bottom-top)
    colors = {"AMD":"#d15c50","MU":"#785bbb","NVDA":"#258aab",
              "DDR4 retail":"#47a377","DDR5 retail":"#9651a7","Consumer GPU retail":"#e18b3e"}
    panel_keys = [
        [("AMD","AMD_mean_jev_pressure"),("MU","MU_mean_jev_pressure"),("NVDA","NVDA_mean_jev_pressure")],
        [("AMD","AMD_stock_change_pct"),("MU","MU_stock_change_pct"),("NVDA","NVDA_stock_change_pct")],
        [("DDR4 retail","DDR4 retail_change_pct"),("DDR5 retail","DDR5 retail_change_pct"),
         ("Consumer GPU retail","Consumer GPU retail_change_pct")],
    ]
    ticks = [[-0.04,0,0.04,0.08,0.12],[-30,-15,0,15,30],[-10,0,10]]
    for panel_index,panel in enumerate(panels):
        top,bottom,_,_,title,unit=panel
        parts.append(f'<text x="45" y="{top-19}" class="label">{title}</text>')
        parts.append(f'<text x="{width-45}" y="{top-19}" text-anchor="end" class="tick">{unit}</text>')
        for tick in ticks[panel_index]:
            y=y_pos(tick,panel)
            parts.append(f'<line x1="150" y1="{y:.1f}" x2="1160" y2="{y:.1f}" stroke="#{"9aa8b5" if tick == 0 else "e8edf0"}"/>')
            label=f"{tick:g}" if panel_index==0 else f"{tick:+g}%"
            parts.append(f'<text x="138" y="{y+4:.1f}" text-anchor="end" class="tick">{label}</text>')
        for group_x,month,row in zip(x_groups,MONTHS,rows):
            for series_index,(name,key) in enumerate(panel_keys[panel_index]):
                value=row[key]
                x=group_x+series_index*48-48
                zero=y_pos(0,panel)
                endpoint=y_pos(value,panel)
                parts.append(f'<rect x="{x}" y="{min(zero,endpoint):.1f}" width="32" height="{max(abs(endpoint-zero),1):.1f}" fill="{colors[name]}" rx="2"/>')
                label=f"{value:+.3f}" if panel_index==0 else f"{value:+.1f}%"
                label_y=endpoint-7 if value>=0 else endpoint+17
                parts.append(f'<text x="{x+16}" y="{label_y:.1f}" text-anchor="middle" class="value">{label}</text>')
            if panel_index==2:
                parts.append(f'<text x="{group_x}" y="{bottom+27}" text-anchor="middle" class="label">{month}</text>')
    legend=[("AMD","AMD stock / news"),("MU","MU stock / news"),("NVDA","NVDA stock / news"),
            ("DDR4 retail","DDR4"),("DDR5 retail","DDR5"),("Consumer GPU retail","Consumer GPU")]
    for x,(name,label) in zip([45,230,410,620,755,885],legend):
        parts.append(f'<rect x="{x}" y="795" width="15" height="15" fill="{colors[name]}"/>')
        parts.append(f'<text x="{x+22}" y="808" class="tick">{label}</text>')
    parts.append('</svg>')
    SVG.write_text("\n".join(parts))
    print(SVG)
    print(CSV)


if __name__ == "__main__":
    main()
