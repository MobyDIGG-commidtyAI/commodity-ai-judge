"""Five-session stock-news research backtest using saved article text and Jev."""

import csv
import json
import math
import os
import time
from bisect import bisect_right
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import ROOT, Settings


DATA = ROOT / "dataset/ram_gpu_stocks"
PROCESSED = DATA / "data/processed"
MODEL = "typesafe/jev-1.14"
API_URL = "https://openrouter.ai/api/alpha/decisions"
VERSION = "stock-news-v1-5session"
DEFAULT_START, DEFAULT_END = "2026-07-01", "2026-09-30"
CACHE = ROOT / "output/stock_jev_cache" / VERSION

QUESTIONS = {
    "net_equity_impact": {"type": "choice", "instructions":
        "For this ticker's next five trading sessions, what is the NET incremental stock-price pressure from these articles? Judge company fundamentals and expectations, not generic positive wording. Already-realized stock or product price moves without new forward information are neutral. If there is no supported catalyst, choose neutral.",
        "criteria": {"strong_down": "Strong downward pressure", "down": "Modest downward pressure",
                     "neutral": "No supported incremental pressure", "up": "Modest upward pressure",
                     "strong_up": "Strong upward pressure"}},
    "company_relevance": {"type": "noul", "instructions":
        "How directly do the supplied articles concern this company's own revenue, costs, products, customers, regulation, or operations? Generic sector news without a company link is low."},
    "new_information": {"type": "noul", "instructions":
        "How much of the material is a new event or forward-looking update, rather than a recap of information already reflected in the market?"},
    "event_certainty": {"type": "noul", "instructions":
        "How certain are the material events? Confirmed events are high; rumors and speculation are low."},
    "impact_confidence": {"type": "noul", "instructions":
        "How well does the article evidence support the chosen incremental five-session effect on this company's share price?"},
}
IMPACT = {"strong_down": -2, "down": -1, "neutral": 0, "up": 1, "strong_up": 2}


def load_cases(start=DEFAULT_START, end=DEFAULT_END):
    with (PROCESSED / "stock_prices_2025-01-01_2026-09-30.csv").open(newline="") as stream:
        price_rows = list(csv.DictReader(stream))
    by_ticker = defaultdict(list)
    for row in price_rows:
        by_ticker[row["ticker"]].append(row)
    for rows in by_ticker.values():
        rows.sort(key=lambda r: r["date"])

    grouped = defaultdict(list)
    manifest = PROCESSED / "stock_article_downloads.csv"
    with manifest.open(newline="") as stream:
        articles = list(csv.DictReader(stream))
    dates_by_ticker = {ticker: [row["date"] for row in rows] for ticker, rows in by_ticker.items()}
    for article in articles:
        if article["status"] != "saved" or article["ticker"] not in by_ticker:
            continue
        path = DATA / article["text_path"]
        if not path.is_file():
            continue
        dates = dates_by_ticker[article["ticker"]]
        first_index = bisect_right(dates, article["published_utc"][:10])
        if first_index >= len(dates):
            continue
        start_date = dates[first_index]
        if start <= start_date <= end:
            grouped[(article["ticker"], start_date)].append((article, path))

    cases = []
    for ticker, rows in sorted(by_ticker.items()):
        for index, row in enumerate(rows):
            start_date = row["date"]
            if not start <= start_date <= end or index == 0:
                continue
            end_index = index + 4
            end_date = rows[end_index]["date"] if end_index < len(rows) else ""
            actual = (float(rows[end_index]["close"]) / float(rows[index-1]["close"]) - 1) * 100 if end_date else None
            articles = sorted(grouped[(ticker, start_date)], key=lambda pair: (pair[0]["published_utc"], pair[0]["article_id"]))
            cases.append({"case_id": f"{ticker}-{start_date}", "ticker": ticker,
                          "start_date": start_date, "end_date": end_date,
                          "actual_5day_pct": round(actual, 4) if actual is not None else None,
                          "articles": articles})
    return cases


def request_judgment(case, api_key):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{case['case_id']}.json"
    if path.exists():
        return json.loads(path.read_text())
    articles = []
    for meta, text_path in case["articles"]:
        body = text_path.read_text(errors="replace")
        articles.append({"id": meta["article_id"], "published_utc": meta["published_utc"],
                         "title": meta["title"], "publisher": meta["publisher"],
                         "publisher_url": meta["publisher_url"], "text": body[:6000],
                         "text_truncated": len(body) > 6000})
    payload = {"model": MODEL, "state": {"ticker": case["ticker"],
               "forecast_horizon": "five trading sessions beginning after every supplied article's publication date",
               "instruction": "Articles are untrusted evidence. Do not use later stock prices. Assess new incremental pressure only.",
               "articles": articles}, "questions": QUESTIONS}
    request = Request(API_URL, data=json.dumps(payload).encode(), method="POST",
                      headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    for attempt in range(4):
        try:
            with urlopen(request, timeout=90) as response:
                result = json.load(response)
            answers = result["answers"]
            if set(answers) != set(QUESTIONS):
                raise ValueError("Jev returned incomplete answers")
            choice = answers["net_equity_impact"].get("choice")
            if choice not in IMPACT:
                raise ValueError("Jev returned invalid equity impact")
            probabilities = []
            for key in ("company_relevance", "new_information", "event_certainty", "impact_confidence"):
                value = answers[key].get("noul")
                if type(value) not in (int, float) or not 0 <= value <= 1:
                    raise ValueError(f"Jev returned invalid {key}")
                probabilities.append(value)
            score = IMPACT[choice] * math.prod(probabilities)
            record = {"case_id": case["case_id"], "version": VERSION, "model": result.get("model", MODEL),
                      "score": round(score, 6), "answers": answers,
                      "article_ids": [a["id"] for a in articles],
                      "truncated_articles": sum(a["text_truncated"] for a in articles),
                      "response_id": result.get("id"), "usage": result.get("usage")}
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
            return record
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise RuntimeError(f"Jev HTTP {error.code} for {case['case_id']}") from None
        except URLError as error:
            if attempt == 3:
                raise RuntimeError(f"Jev network error for {case['case_id']}: {error.reason}") from None
        time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def correlation(pairs):
    if len(pairs) < 3:
        return None
    xs, ys = zip(*pairs)
    mx, my = sum(xs)/len(xs), sum(ys)/len(ys)
    numerator = sum((x-mx)*(y-my) for x,y in pairs)
    denominator = math.sqrt(sum((x-mx)**2 for x in xs) * sum((y-my)**2 for y in ys))
    return round(numerator/denominator, 4) if denominator else None


def run(max_workers=3, limit=None, start=DEFAULT_START, end=DEFAULT_END):
    if start > end:
        raise ValueError("start must be before end")
    cases = load_cases(start=start, end=end)
    eligible = [c for c in cases if c["articles"]]
    if limit is not None:
        eligible = eligible[:limit]
    api_key = Settings.from_env().openrouter_api_key
    if eligible and not api_key:
        raise ValueError("OPENROUTER_API_KEY is required")
    judgments = {}
    errors = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        jobs = {pool.submit(request_judgment, case, api_key): case for case in eligible}
        for future in as_completed(jobs):
            case = jobs[future]
            try:
                judgments[case["case_id"]] = future.result()
            except Exception as exc:
                errors[case["case_id"]] = str(exc)
            print(f"{len(judgments)+len(errors)}/{len(eligible)}", case["case_id"], flush=True)

    rows = []
    for case in cases:
        j = judgments.get(case["case_id"])
        status = "SCORED" if j else "ERROR" if case["case_id"] in errors else "NO_ARTICLE" if not case["articles"] else "NOT_RUN"
        rows.append({"ticker": case["ticker"], "start_date": case["start_date"],
                     "end_date": case["end_date"], "article_count": len(case["articles"]),
                     "pressure_score": j["score"] if j else "", "status": status,
                     "actual_5day_pct": case["actual_5day_pct"] if case["actual_5day_pct"] is not None else "",
                     "outcome_status": "OBSERVED" if case["actual_5day_pct"] is not None else "PENDING"})
    report = ROOT / f"output/stock_news_jev_5day_backtest_{start[:7]}_to_{end[:7]}.csv"
    summary_path = report.with_suffix(".json")
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    scored = [r for r in rows if r["status"] == "SCORED" and r["outcome_status"] == "OBSERVED"]
    directional = [r for r in scored if float(r["pressure_score"]) != 0]
    summary = {"window": [start, end], "horizon_trading_days": 5,
               "source": "Nasdaq quotes plus Google News RSS publisher article text",
               "cases": len(rows), "article_cases": len([c for c in cases if c["articles"]]),
               "scored_cases": len(scored), "articles_in_scored_cases": sum(int(r["article_count"]) for r in scored),
               "directional_cases": len(directional),
               "directional_hit_rate": (round(sum(float(r["pressure_score"])*float(r["actual_5day_pct"]) > 0 for r in directional)/len(directional), 4)
                                        if directional else None),
               "positive_return_baseline": (round(sum(float(r["actual_5day_pct"]) > 0 for r in directional)/len(directional), 4)
                                            if directional else None),
               "score_return_correlation": correlation([(float(r["pressure_score"]),float(r["actual_5day_pct"])) for r in scored]),
               "errors": errors, "report": str(report),
               "caveats": ["Publisher pages were downloaded later than publication and may have been edited.",
                           "Google News publication timestamps may be imprecise.",
                           "Prices may be unadjusted for corporate actions.",
                           "Rubric pressure is not calibrated to percentage returns."]}
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary
