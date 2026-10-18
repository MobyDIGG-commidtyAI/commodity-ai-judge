"""Explore MU-linked RAM news themes against subsequent monthly retail RAM prices."""

import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "dataset/ram_gpu_stocks/data/processed/stock_article_downloads.csv"
PRICES = ROOT / "dataset/chin/prices/retail-and-cloud-price-contract.json"
OUT_CSV = ROOT / "output/ram_news_theme_vs_next_month_retail_2025-10_to_2026-08.csv"
OUT_JSON = OUT_CSV.with_suffix(".json")
OUT_SVG = ROOT / "output/ram_news_theme_vs_next_month_retail_2025-10_to_2026-08.svg"
MONTHS = [f"{y}-{m:02d}" for y,start,end in ((2025,10,12),(2026,1,8))
          for m in range(start,end+1)]

THEMES = {
    "direct_ram": re.compile(r"\b(?:ddr5|ddr4|ddr modules?|pc ram|consumer ram|memory kits?|dram spot|dram contract)\b", re.I),
    "dram_market": re.compile(r"\b(?:dram|memory chips?|memory prices?|memory shortages?|memory supply)\b", re.I),
    "hbm_ai": re.compile(r"\b(?:hbm|high.bandwidth memory|ai|data.center|servers?)\b", re.I),
    "earnings_stock": re.compile(r"\b(?:earnings|revenue|guidance|shares|stock|analyst|target price)\b", re.I),
    "supply": re.compile(r"\b(?:supply|shortages?|capacity|production|wafer|factory|plant)\b", re.I),
}


def pearson(xs, ys):
    if len(xs) < 3:
        return None
    mx, my = sum(xs)/len(xs), sum(ys)/len(ys)
    numerator = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    denominator = math.sqrt(sum((x-mx)**2 for x in xs)*sum((y-my)**2 for y in ys))
    return round(numerator/denominator, 4) if denominator else None


def main():
    by_month = defaultdict(list)
    with MANIFEST.open(newline="") as stream:
        for item in csv.DictReader(stream):
            if item["ticker"] == "MU" and item["status"] == "saved":
                by_month[item["published_utc"][:7]].append(item)
    raw = json.loads(PRICES.read_text())
    indices = {kind: {r["month"]: float(r["index"]) for r in raw["ram"][kind]}
               for kind in ("ddr4","ddr5")}
    rows=[]
    for month,next_month in zip(MONTHS,MONTHS[1:]+["2026-09"]):
        articles=by_month[month]
        row={"news_month":month,"price_month":next_month,"saved_mu_articles":len(articles)}
        for name,pattern in THEMES.items():
            count=sum(bool(pattern.search(article["title"])) for article in articles)
            row[name+"_headlines"]=count
            row[name+"_share"]=round(count/len(articles),5) if articles else ""
        for kind in ("ddr4","ddr5"):
            row[kind+"_next_month_change_pct"]=round((indices[kind][next_month]/indices[kind][month]-1)*100,2)
        rows.append(row)
    with OUT_CSV.open("w",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    xs=[float(row["direct_ram_share"]) for row in rows]
    ys=[float(row["ddr5_next_month_change_pct"]) for row in rows]
    summary={"news_months":len(rows),"mu_saved_articles_in_news_months":sum(row["saved_mu_articles"] for row in rows),
             "direct_ram_headlines":sum(row["direct_ram_headlines"] for row in rows),
             "correlations_with_next_month_ddr5_change":
             {name:pearson([float(row[name+"_share"]) for row in rows],ys) for name in THEMES},
             "direct_ram_correlation_without_october_2025":pearson(xs[1:],ys[1:]),
             "method":"Simple overlapping title-keyword themes among saved MU-linked articles; not an LLM classification or predictive backtest.",
             "limitations":["Only 11 next-month pairs", "Google News RSS is a ranked, capped sample",
                            "Keyword matches include product announcements and other non-price stories"]}
    OUT_JSON.write_text(json.dumps(summary,indent=2))

    width,height=1320,650
    left,right=115,55
    xs_pos=[left+i*(width-left-right)/(len(rows)-1) for i in range(len(rows))]
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#233445}.title{font-size:26px;font-weight:bold}.sub{font-size:15px;fill:#607181}.label{font-size:17px;font-weight:bold}.tick{font-size:12px;fill:#607181}</style>',
           '<text x="40" y="43" class="title">Does RAM news lead next-month DDR5 retail prices?</text>',
           '<text x="40" y="70" class="sub">MU-linked saved article headlines · publication month vs following month’s DDR5 index change</text>',
           '<text x="40" y="113" class="label">Direct RAM headline share</text>',
           '<text x="40" y="355" class="label">Following-month DDR5 price change</text>']
    top_a,bottom_a,top_b,bottom_b=135,295,380,550
    for tick in (0,5,10,15):
        y=bottom_a-tick/15*(bottom_a-top_a)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="#e6ebef"/>')
        parts.append(f'<text x="{left-12}" y="{y+4:.1f}" text-anchor="end" class="tick">{tick}%</text>')
    for tick in (0,20,40,60,80):
        y=bottom_b-tick/80*(bottom_b-top_b)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="#e6ebef"/>')
        parts.append(f'<text x="{left-12}" y="{y+4:.1f}" text-anchor="end" class="tick">{tick:+g}%</text>')
    for x,row in zip(xs_pos,rows):
        share=float(row["direct_ram_share"])*100
        delta=float(row["ddr5_next_month_change_pct"])
        ya=bottom_a-share/15*(bottom_a-top_a)
        yb=bottom_b-delta/80*(bottom_b-top_b)
        parts.append(f'<rect x="{x-18:.1f}" y="{ya:.1f}" width="36" height="{bottom_a-ya:.1f}" fill="#8c63b6" rx="2"/>')
        parts.append(f'<rect x="{x-18:.1f}" y="{min(yb,bottom_b):.1f}" width="36" height="{abs(bottom_b-yb):.1f}" fill="#d5833e" rx="2"/>')
        parts.append(f'<text x="{x:.1f}" y="{bottom_b+23}" text-anchor="middle" class="tick">{row["news_month"][2:]}</text>')
        parts.append(f'<text x="{x:.1f}" y="{ya-7:.1f}" text-anchor="middle" class="tick">{row["direct_ram_headlines"]}/{row["saved_mu_articles"]}</text>')
    all_r=summary["correlations_with_next_month_ddr5_change"]["direct_ram"]
    excluded_r=summary["direct_ram_correlation_without_october_2025"]
    parts.append(f'<text x="40" y="612" class="sub">Correlation across 11 months: r = {all_r:+.2f}; excluding October 2025: r = {excluded_r:+.2f}. Small, selected sample.</text>')
    parts.append('<text x="40" y="638" class="tick">Purple: headline share. Orange: following-month DDR5 change. Keyword counts are descriptive and cannot establish causality.</text>')
    parts.append('</svg>')
    OUT_SVG.write_text("\n".join(parts))
    print(OUT_CSV);print(OUT_JSON);print(OUT_SVG)
    print(json.dumps(summary,indent=2))


if __name__=="__main__":
    main()
