"""Inspect saved MU article bodies for consumer RAM price-pressure evidence."""

import argparse
import csv
import html
import json
import math
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "dataset/ram_gpu_stocks/data/processed/stock_article_downloads.csv"
PRICES = ROOT / "dataset/chin/prices/retail-and-cloud-price-contract.json"
OUT = ROOT / "output/ram_full_article_pressure_2025-10_to_2026-08"
RAM = re.compile(r"\b(?:ddr[45]|consumer ram|pc ram|desktop ram|ram (?:kit|module|price)|memory (?:kit|module|stick))s?\b", re.I)
PRICE = re.compile(r"\b(?:prices?|costs?|retail|expensiv\w*|cheaper|affordab\w*|hikes?|quotations?|shortages?)\b", re.I)
UP = re.compile(r"\b(?:ris(?:e|en|ing)|rose|increas\w*|higher|hikes?|surge\w*|jump\w*|spik\w*|soar\w*|shortag\w*|tight\w*|scarce|expensiv\w*|record high)\b", re.I)
DOWN = re.compile(r"\b(?:fall\w*|fell|declin\w*|decreas\w*|drop\w*|lower|cheaper|eas(?:e|ing)|plung\w*|slump\w*|overstock|surplus)\b", re.I)


def corr(xs, ys):
    if len(xs) < 3:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = math.sqrt(sum((x-mx)**2 for x in xs) * sum((y-my)**2 for y in ys))
    return round(sum((x-mx)*(y-my) for x, y in zip(xs, ys)) / den, 4) if den else None


def evidence(text):
    # The archive often ends with recommendations, author biographies, and site chrome.
    # Restrict matching to the article's opening 6,000 characters; retain full files on disk.
    opening = text[:6000]
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", opening)]
    sentences = [sentence.strip() for p in paragraphs for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", p)]
    matches = []
    for sentence in sentences:
        ram_hits, price_hits = list(RAM.finditer(sentence)), list(PRICE.finditer(sentence))
        if any(abs(r.start() - p.start()) <= 120 for r in ram_hits for p in price_hits):
            matches.append(sentence)
    up = [sentence for sentence in matches if UP.search(sentence)]
    down = [sentence for sentence in matches if DOWN.search(sentence)]
    if up and not down:
        label = "up"
    elif down and not up:
        label = "down"
    elif up and down:
        label = "mixed"
    elif matches:
        label = "price_mention"
    else:
        label = "no_direct_consumer_price_evidence"
    return label, (matches[0][:400] if matches else "")


def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-10", help="First news month, e.g. 2024-10")
    args = parser.parse_args()
    start_year, start_month = map(int, args.start.split("-"))
    MONTHS = [f"{y}-{m:02d}" for y in range(start_year, 2027)
              for m in range(1, 13) if (y, m) >= (start_year, start_month) and (y, m) <= (2026, 8)]
    OUT = ROOT / f"output/ram_full_article_pressure_{MONTHS[0]}_to_{MONTHS[-1]}"
    articles = []
    with MANIFEST.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row["ticker"] != "MU" or row["published_utc"][:7] not in MONTHS:
                continue
            item = {key: row[key] for key in ("article_id", "published_utc", "title", "publisher_url", "status", "text_path")}
            item["month"] = row["published_utc"][:7]
            if row["status"] == "saved" and row["text_path"]:
                path = ROOT / "dataset/ram_gpu_stocks" / row["text_path"]
                if path.is_file():
                    text = path.read_text(errors="replace")
                    item["label"], item["evidence_excerpt"] = evidence(text)
                    item["characters"] = len(text)
                else:
                    item["label"], item["evidence_excerpt"], item["characters"] = "missing_file", "", 0
            else:
                item["label"], item["evidence_excerpt"], item["characters"] = "unavailable", "", 0
            articles.append(item)

    by_month = defaultdict(list)
    for item in articles:
        by_month[item["month"]].append(item)
    raw = json.loads(PRICES.read_text())
    ddr5 = {row["month"]: float(row["index"]) for row in raw["ram"]["ddr5"]}
    monthly = []
    for month, following in zip(MONTHS, MONTHS[1:] + ["2026-09"]):
        group = by_month[month]
        available = [a for a in group if a["label"] not in ("unavailable", "missing_file")]
        counts = {label: sum(a["label"] == label for a in available) for label in
                  ("up", "down", "mixed", "price_mention", "no_direct_consumer_price_evidence")}
        monthly.append({"news_month": month, "price_month": following,
                        "mu_links": len(group), "saved_full_articles": len(available),
                        **counts,
                        "up_share": round(counts["up"] / len(available), 5) if available else 0,
                        "pressure_balance": round((counts["up"] - counts["down"]) / len(available), 5) if available else 0,
                        "next_month_ddr5_change_pct": round(100 * (ddr5[following] / ddr5[month] - 1), 2)})

    OUT.parent.mkdir(exist_ok=True)
    for path, rows in ((OUT.with_name(OUT.name + "_articles.csv"), articles),
                       (OUT.with_name(OUT.name + "_monthly.csv"), monthly)):
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    covered = [r for r in monthly if r["saved_full_articles"]]
    ys = [r["next_month_ddr5_change_pct"] for r in covered]
    summary = {"method": "Rule-based sentence matching in the first 6,000 characters of saved article text; exploratory, not an LLM judge or causal backtest",
               "news_months": len(monthly), "months_with_saved_articles": len(covered),
               "months_without_saved_articles": [r["news_month"] for r in monthly if not r["saved_full_articles"]],
               "mu_links": len(articles), "saved_full_articles": sum(r["saved_full_articles"] for r in monthly),
               "labels": {label: sum(r[label] for r in monthly) for label in
                          ("up", "down", "mixed", "price_mention", "no_direct_consumer_price_evidence")},
               "up_share_correlation_next_month_ddr5": corr([r["up_share"] for r in covered], ys),
               "up_share_correlation_excluding_october_2025": corr([r["up_share"] for r in covered if r["news_month"] != "2025-10"],
                                                                     [r["next_month_ddr5_change_pct"] for r in covered if r["news_month"] != "2025-10"]),
               "pressure_balance_correlation_next_month_ddr5": corr([r["pressure_balance"] for r in covered], ys)}
    OUT.with_suffix(".json").write_text(json.dumps(summary, indent=2))
    write_chart(monthly, summary)
    print(json.dumps(summary, indent=2))


def write_chart(monthly, summary):
    width, height = max(1380, 90 * len(monthly) + 200), 760
    left, right = 110, 55
    xs = [left + i * (width-left-right) / (len(monthly)-1) for i in range(len(monthly))]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
             '<rect width="100%" height="100%" fill="#fbfcfe"/>',
             '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#233445}.title{font-size:26px;font-weight:bold}.sub{font-size:15px;fill:#607181}.label{font-size:18px;font-weight:bold}.tick{font-size:13px;fill:#607181}.note{font-size:14px;fill:#405467}</style>',
             '<text x="45" y="42" class="title">RAM article pressure and subsequent DDR5 retail prices</text>',
             f'<text x="45" y="69" class="sub">News published {monthly[0]["news_month"]}–{monthly[-1]["news_month"]}; each price bar shows the change in the following month</text>',
             '<text x="45" y="113" class="label">Share of saved MU articles with direct RAM price evidence</text>',
             '<text x="45" y="365" class="label">Following-month DDR5 retail price change</text>']
    top1, bottom1, top2, bottom2 = 145, 310, 395, 590
    for tick in (0, 10, 20, 30):
        y = bottom1 - tick / 30 * (bottom1-top1)
        parts += [f'<line x1="{left}" x2="{width-right}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e3e8ed"/>',
                  f'<text x="{left-14}" y="{y+5:.1f}" text-anchor="end" class="tick">{tick}%</text>']
    for tick in (0, 20, 40, 60, 80):
        y = bottom2 - tick / 80 * (bottom2-top2)
        parts += [f'<line x1="{left}" x2="{width-right}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e3e8ed"/>',
                  f'<text x="{left-14}" y="{y+5:.1f}" text-anchor="end" class="tick">{tick}%</text>']
    for x, row in zip(xs, monthly):
        n = row["saved_full_articles"]
        up = 100 * row["up"] / n if n else 0
        down = 100 * row["down"] / n if n else 0
        up_y = bottom1-up/30*(bottom1-top1)
        down_y = bottom1-down/30*(bottom1-top1)
        price = row["next_month_ddr5_change_pct"]
        price_y = bottom2-price/80*(bottom2-top2)
        count_label = f"{row['up']}/{n}" if n else "no news"
        parts += [f'<rect x="{x-18:.1f}" y="{up_y:.1f}" width="18" height="{bottom1-up_y:.1f}" fill="#a75446"/>',
                  f'<rect x="{x:.1f}" y="{down_y:.1f}" width="18" height="{bottom1-down_y:.1f}" fill="#427ca4"/>',
                  f'<text x="{x:.1f}" y="{up_y-8:.1f}" text-anchor="middle" class="tick">{count_label}</text>',
                  f'<rect x="{x-18:.1f}" y="{min(price_y,bottom2):.1f}" width="36" height="{abs(bottom2-price_y):.1f}" fill="#b58437" rx="2"/>',
                  f'<text x="{x:.1f}" y="{min(price_y,bottom2)-8:.1f}" text-anchor="middle" class="tick">{price:+.1f}%</text>',
                  f'<text x="{x:.1f}" y="{bottom2+28}" text-anchor="middle" class="tick">{html.escape(row["news_month"][2:])}</text>']
    parts += ['<rect x="45" y="660" width="16" height="12" fill="#a75446"/><text x="68" y="671" class="note">Upward RAM price evidence</text>',
              '<rect x="325" y="660" width="16" height="12" fill="#427ca4"/><text x="348" y="671" class="note">Downward RAM price evidence</text>',
              '<rect x="625" y="660" width="16" height="12" fill="#b58437"/><text x="648" y="671" class="note">Next-month DDR5 retail change</text>',
              f'<text x="45" y="708" class="note">{summary["saved_full_articles"]} saved articles; up-share correlation with following-month change: r = {summary["up_share_correlation_next_month_ddr5"]:+.2f} across {summary["months_with_saved_articles"]} covered months.</text>',
              '<text x="45" y="734" class="tick">Exploratory rule-based matches in article text. Some reports describe price rises already underway; this is not a validated forecast.</text>',
              '</svg>']
    OUT.with_suffix(".svg").write_text("\n".join(parts))


if __name__ == "__main__":
    main()
