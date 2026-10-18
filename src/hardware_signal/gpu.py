"""Consumer GPU retail-index cases and a GPU-specific Jev article rubric."""

import csv
import json
import os
from pathlib import Path
from collections import defaultdict

from .cases import next_month
from .jev import JevJudge, _choice


GPU_CATEGORIES = {
    "consumer_gpu_price_change": "Announced consumer graphics-card price change",
    "consumer_gpu_supply": "Change in consumer graphics-card availability",
    "consumer_gpu_demand": "Change in consumer graphics-card buying demand",
    "gpu_component_cost": "Component or manufacturing cost of consumer graphics cards",
    "ai_server_gpu": "AI server or data-center GPU market, without a stated consumer-card link",
    "trade_policy": "Tariff, export restriction, or trade-policy change",
    "other": "No matching category",
}

GPU_QUESTIONS = {
    "supply_impact": _choice(
        "What article-supported change in consumer graphics-card retail supply is expected? Positive means less supply and upward retail price pressure. AI servers alone do not establish a consumer-card effect.",
        {"minus_2": "Strong increase in consumer GPU supply", "minus_1": "Modest increase in consumer GPU supply",
         "zero": "No supported consumer GPU supply change", "plus_1": "Modest reduction in consumer GPU supply",
         "plus_2": "Strong reduction in consumer GPU supply"}),
    "demand_impact": _choice(
        "What article-supported change in consumer graphics-card buying demand is expected? Positive means more demand and upward retail price pressure.",
        {"minus_2": "Strong consumer GPU demand decline", "minus_1": "Modest consumer GPU demand decline",
         "zero": "No supported consumer GPU demand change", "plus_1": "Modest consumer GPU demand growth",
         "plus_2": "Strong consumer GPU demand growth"}),
    "production_disruption": _choice(
        "What unplanned physical interruption to consumer GPU production is reported? Planned capacity changes do not count.",
        {"0": "None", "1": "Brief localized issue", "2": "Material plant interruption",
         "3": "Major multi-day outage", "4": "Severe multi-site or prolonged loss"}),
    "market_scope": _choice(
        "What is the scope of the supported consumer graphics-card price effect? AI server systems alone are irrelevant to the consumer GPU retail index.",
        {"0": "No supported consumer GPU price effect", "1": "One vendor",
         "2": "One consumer GPU product segment", "3": "Consumer GPU market",
         "4": "Global graphics-card supply chain"}),
    "duration_horizon": _choice(
        "How long is the article-supported consumer GPU price effect expected to persist?",
        {"0": "Less than one week", "1": "One week to less than a month",
         "2": "One to three months", "3": "Over three to twelve months", "4": "Over one year"}),
    "event_category": _choice("Which category best describes this article?", GPU_CATEGORIES),
    "event_certainty": {"type": "noul", "instructions":
        "Is the described event confirmed to have occurred, or firmly scheduled by a credible source? Rumors are false."},
    "impact_confidence": {"type": "noul", "instructions":
        "Does the article provide direct and specific evidence for its claimed effect on consumer graphics-card retail supply or demand? AI server GPU pricing without a consumer-card link is false."},
}


class GpuJevJudge(JevJudge):
    questions = GPU_QUESTIONS
    target = "next-month consumer GPU retail price index"
    rubric_version = "gpu-rubric-v1-jev-article"


def load_gpu_prices(data_dir):
    data = json.loads((data_dir / "prices/retail-and-cloud-price-contract.json").read_text())
    return {row["month"]: float(row["index"]) for row in data["gpuRetail"]}


def build_gpu_cases(settings):
    prices = load_gpu_prices(settings.data_dir)
    news = defaultdict(list)
    with (settings.data_dir / "news/articles.csv").open(newline="") as handle:
        for number, row in enumerate(csv.DictReader(handle), 1):
            if row["product"] == "gpu":
                news[row["published_at"][:7]].append({
                    "id": f"article-{number}", "date": row["published_at"][:10],
                    "title": row["title"], "source": row["source"], "url": row["url"]})
    cases = []
    for month in sorted(prices):
        target = next_month(month)
        if target in prices:
            articles = sorted(news.get(month, []), key=lambda a: (a["date"], a["id"]))[:settings.max_articles]
            cases.append({"case_id": f"gpu-{month}", "as_of_month": month,
                          "target_month": target, "news": articles})
    return cases


def build_ohm_gpu_cases(settings, include_pending=False):
    """Build article-eligible GPU cases from the newer OHM news feed."""
    prices = load_gpu_prices(settings.data_dir)
    news = defaultdict(list)
    path = Path(os.environ.get("NEWS_FEED", settings.data_dir.parent / "ohm/news_feed.csv"))
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for number, row in enumerate(csv.DictReader(handle), 2):
            if row["category"] != "GPU" or not row["url"].strip():
                continue
            news[row["ts"][:7]].append({
                "id": f"ohm-{number}", "date": row["ts"][:10],
                "title": row["title"], "source": row["source"],
                "url": row["url"], "genre": row["genre"]})
    cases = []
    months = set(prices)
    if include_pending:
        months.update(m for m in news if m >= min(prices))
    for month in sorted(months):
        target = next_month(month)
        if target in prices or include_pending:
            articles = sorted(news.get(month, []), key=lambda a: (a["date"], a["id"]))
            cases.append({"case_id": f"ohm-gpu-{month}", "as_of_month": month,
                          "target_month": target, "news": articles})
    return cases
