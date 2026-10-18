"""Plot one-year stock-news pressure and monthly stock/retail price deltas."""

import csv
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MONTHS = [f"{year}-{month:02d}" for year, start, stop in ((2025, 10, 12), (2026, 1, 9))
          for month in range(start, stop+1)]
PRIOR = "2025-09"
REPORT = ROOT / "output/stock_news_jev_5day_backtest_2025-10_to_2026-09.csv"
SVG = ROOT / "output/stock_news_vs_ram_gpu_monthly_deltas_2025-10_to_2026-09.svg"
TABLE = ROOT / "output/stock_news_vs_ram_gpu_monthly_deltas_2025-10_to_2026-09.csv"


def main():
    data = json.loads((ROOT / "dataset/chin/prices/retail-and-cloud-price-contract.json").read_text())
    retail = {"DDR4": {r["month"]: float(r["index"]) for r in data["ram"]["ddr4"]},
              "DDR5": {r["month"]: float(r["index"]) for r in data["ram"]["ddr5"]},
              "Consumer GPU": {r["month"]: float(r["index"]) for r in data["gpuRetail"]}}
    stocks = defaultdict(dict)
    with (ROOT / "dataset/ram_gpu_stocks/data/processed/stock_prices_2025-01-01_2026-09-30.csv").open(newline="") as stream:
        for item in csv.DictReader(stream):
            if item["date"][:7] in MONTHS or item["date"][:7] == PRIOR:
                stocks[item["ticker"]][item["date"][:7]] = float(item["close"])
    pressures = defaultdict(list)
    with REPORT.open(newline="") as stream:
        for item in csv.DictReader(stream):
            if item["status"] == "SCORED":
                pressures[(item["ticker"],item["start_date"][:7])].append(float(item["pressure_score"]))
    rows = []
    for i,month in enumerate(MONTHS):
        previous = MONTHS[i-1] if i else PRIOR
        row = {"month":month}
        for ticker in ("AMD","MU","NVDA"):
            scores=pressures[(ticker,month)]
            row[f"{ticker}_pressure_mean"] = round(sum(scores)/len(scores),5) if scores else ""
            row[f"{ticker}_scored_days"] = len(scores)
            row[f"{ticker}_stock_delta_pct"] = round((stocks[ticker][month]/stocks[ticker][previous]-1)*100,2)
        for name,series in retail.items():
            row[f"{name}_retail_delta_pct"] = round((series[month]/series[previous]-1)*100,2)
        rows.append(row)
    with TABLE.open("w",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)

    width,height=1580,1050
    left,right=155,50
    xs=[left+i*(width-left-right)/(len(MONTHS)-1) for i in range(len(MONTHS))]
    panels=[(145,325,-0.04,0.16,"Mean Jev stock-news pressure","rubric score"),
            (420,665,-35,100,"Monthly stock closing-price change","% month over month"),
            (760,950,-15,80,"Monthly retail price-index change","% month over month")]
    colors={"AMD":"#d3594e","MU":"#7959bd","NVDA":"#2589a9",
            "DDR4":"#46a375","DDR5":"#9652a8","Consumer GPU":"#df873d"}
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#243445}.title{font-size:29px;font-weight:bold}.sub{font-size:16px;fill:#607181}.label{font-size:18px;font-weight:bold}.tick{font-size:12px;fill:#607181}</style>',
           '<text x="45" y="45" class="title">One year: stock-news pressure and stock / hardware price changes</text>',
           '<text x="45" y="75" class="sub">October 2025–September 2026 · Jev predicts 5-session stock pressure; retail RAM/GPU prices are separate monthly targets</text>']
    def y(value,p):
        top,bottom,low,high,_,_=p
        return bottom-(value-low)/(high-low)*(bottom-top)
    for index,p in enumerate(panels):
        top,bottom,low,high,title,unit=p
        parts.append(f'<text x="45" y="{top-23}" class="label">{title}</text>')
        parts.append(f'<text x="{width-50}" y="{top-23}" text-anchor="end" class="tick">{unit}</text>')
        ticks=([-0.04,0,0.04,0.08,0.12,0.16] if index==0 else
               [-25,0,25,50,75,100] if index==1 else [-10,0,20,40,60,80])
        for tick in ticks:
            yy=y(tick,p)
            if top <= yy <= bottom:
                parts.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{width-right}" y2="{yy:.1f}" stroke="#{"9aa9b7" if tick==0 else "e8edf0"}"/>')
                parts.append(f'<text x="{left-12}" y="{yy+4:.1f}" text-anchor="end" class="tick">{tick:g}{"" if index==0 else "%"}</text>')
        for xx,month in zip(xs,MONTHS):
            parts.append(f'<text x="{xx:.1f}" y="{bottom+23}" text-anchor="middle" class="tick">{month[2:]}</text>')
    panels_series=[[(name,f"{name}_pressure_mean") for name in ("AMD","MU","NVDA")],
                   [(name,f"{name}_stock_delta_pct") for name in ("AMD","MU","NVDA")],
                   [(name,f"{name}_retail_delta_pct") for name in ("DDR4","DDR5","Consumer GPU")]]
    for p,series in zip(panels,panels_series):
        for name,key in series:
            points=[(xx,y(float(row[key]),p)) for xx,row in zip(xs,rows) if row[key] != ""]
            coords=" ".join(f"{xx:.1f},{yy:.1f}" for xx,yy in points)
            parts.append(f'<polyline points="{coords}" fill="none" stroke="{colors[name]}" stroke-width="2.8" stroke-linejoin="round"/>')
            for xx,yy in points:
                parts.append(f'<circle cx="{xx:.1f}" cy="{yy:.1f}" r="3.8" fill="{colors[name]}"/>')
    for x,name,label in [(55,"AMD","AMD stock / news"),(325,"MU","MU stock / news"),
                         (585,"NVDA","NVDA stock / news"),(855,"DDR4","DDR4 retail"),
                         (1060,"DDR5","DDR5 retail"),(1250,"Consumer GPU","Consumer GPU retail")]:
        parts.append(f'<line x1="{x}" y1="1010" x2="{x+25}" y2="1010" stroke="{colors[name]}" stroke-width="4"/>')
        parts.append(f'<text x="{x+33}" y="1015" class="tick">{label}</text>')
    parts.append('<text x="45" y="1040" class="tick">Pressure is averaged over scored ticker-days in each month; prices are month-end stock closes or monthly retail index readings.</text>')
    parts.append('</svg>')
    SVG.write_text("\n".join(parts))
    print(SVG)
    print(TABLE)


if __name__=="__main__":
    main()
