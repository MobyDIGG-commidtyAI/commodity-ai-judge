"""Plot monthly OHM GPU URL, saved-page, and extracted-article counts."""

import csv
import html
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dataset/ohm/news_feed.csv"
DOWNLOADS = ROOT / "output/ohm_gpu_page_downloads_all_history.json"
CACHE = ROOT / "output/article_cache"
OUTPUT = ROOT / "output/ohm_gpu_article_availability_by_month.svg"


def main() -> None:
    downloads = {r["article_id"]: r for r in json.loads(DOWNLOADS.read_text())}
    counts = defaultdict(Counter)
    with DATA.open(newline="", encoding="utf-8-sig") as stream:
        for line, row in enumerate(csv.DictReader(stream), 2):
            month = row["ts"][:7]
            if row["category"] != "GPU" or not row["url"].strip() or not ("2024-05" <= month <= "2026-10"):
                continue
            c = counts[month]
            c["url"] += 1
            article_id = f"ohm-{line}"
            if downloads.get(article_id, {}).get("status") in ("saved", "already_saved"):
                c["saved"] += 1
            cache_file = CACHE / f"{article_id}.json"
            if cache_file.exists() and json.loads(cache_file.read_text()).get("status") == "ok":
                c["text"] += 1

    months = sorted(counts)
    width, height = 1100, 670
    left, chart_width = 180, 780
    max_value = max(c["url"] for c in counts.values())
    scale = chart_width / max_value
    pieces = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
              '<rect width="100%" height="100%" fill="white"/>',
              '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#233345}.title{font-size:27px;font-weight:bold}.sub{font-size:16px;fill:#607082}.month{font-size:17px;font-weight:bold}.count{font-size:13px}</style>',
              '<text x="40" y="46" class="title">OHM GPU articles available by dataset month</text>',
              '<text x="40" y="75" class="sub">May 2024–October 2026 · months with at least one GPU URL</text>']
    for i, month in enumerate(months):
        y = 115 + i * 53
        c = counts[month]
        pieces.append(f'<text x="40" y="{y+22}" class="month">{html.escape(month)}</text>')
        for offset, key, color in ((0, "url", "#aab5c1"), (14, "saved", "#3a81ba"), (28, "text", "#e6a52e")):
            value = c[key]
            if value:
                bar_width = max(value * scale, 3)
                pieces.append(f'<rect x="{left}" y="{y+offset}" width="{bar_width:.1f}" height="11" rx="2" fill="{color}"/>')
                pieces.append(f'<text x="{left+bar_width+6:.1f}" y="{y+offset+10}" class="count">{value}</text>')
    legend_y = 610
    for x, color, label in ((40, "#aab5c1", "Dataset URL"), (225, "#3a81ba", "HTML page saved"), (460, "#e6a52e", "Article text extracted")):
        pieces.append(f'<rect x="{x}" y="{legend_y}" width="17" height="13" rx="2" fill="{color}"/>')
        pieces.append(f'<text x="{x+25}" y="{legend_y+12}" class="sub">{label}</text>')
    pieces.append('<text x="40" y="651" class="sub">125 URLs · 123 pages saved · 10 readable articles; 5 met the backtest date requirement.</text>')
    pieces.append('</svg>')
    OUTPUT.write_text("\n".join(pieces))
    print(OUTPUT)
    for month in months:
        print(month, dict(counts[month]))


if __name__ == "__main__":
    main()
