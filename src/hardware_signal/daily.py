"""Daily run for the live service: judge this month's news for DDR5 and consumer GPUs, write judge.json.

DDR5 uses the eight-dimension headline rubric (one OpenRouter chat call, OPENROUTER_MODEL). GPU uses the
GPU-specific Jev article rubric on dated, fetched article text (one Decisions API call per article, capped).
The output is a signed news price-pressure score per category for the API to show next to the price
evidence. It is not a calibrated price forecast (see README, Research limits).
"""

import csv
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .article_cache import fetch_article, load_cached_article, save_article, with_article_text
from .cases import next_month
from .config import OUTPUT_DIR
from .gpu import GpuJevJudge, build_ohm_gpu_cases
from .openrouter import OpenRouterJudge
from .storage import JudgmentStore

log = logging.getLogger("hardware_signal.daily")
SCHEMA_VERSION = 1
LIMITATIONS = [
    "Signed news price-pressure score from an LLM rubric; not calibrated to a percentage price forecast.",
    "Backtests in this repo do not yet show predictive accuracy; treat it as context next to the price evidence.",
    "DDR5 is judged from headlines; GPU only from dated article text that could be fetched.",
]


def news_feed_path(settings):
    return Path(os.environ.get("NEWS_FEED", settings.data_dir.parent / "ohm/news_feed.csv"))


def load_feed(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row, row_number=number) for number, row in enumerate(csv.DictReader(handle), 2)]


def latest_month(rows):
    months = [row["ts"][:7] for row in rows if row.get("ts")]
    if not months:
        raise ValueError("news feed has no dated rows")
    return max(months)


def ram_case(rows, month, max_articles):
    """Pending DDR5 case: the month's RAM headlines from the live news feed."""
    news = sorted(({"id": f"feed-{row['row_number']}", "date": row["ts"][:10], "title": row["title"],
                    "source": row["source"], "url": row["url"]}
                   for row in rows if row.get("category") == "RAM" and row["ts"][:7] == month and row["title"]),
                  key=lambda a: (a["date"], a["id"]))
    return {"case_id": f"ddr5-{month}", "as_of_month": month, "target_month": next_month(month),
            "news": news[-max_articles:] if max_articles else news}


def gpu_case(settings, month, max_articles, fetch=fetch_article, max_fetch=40):
    """Pending GPU case for the month, enriched with dated article text (fetched once, then cached).
    Fetching is free, so up to max_fetch links are tried; only the newest max_articles readable ones are judged."""
    cases = {c["as_of_month"]: c for c in build_ohm_gpu_cases(settings, include_pending=True)}
    case = cases.get(month) or {"case_id": f"ohm-gpu-{month}", "as_of_month": month,
                                "target_month": next_month(month), "news": []}
    case = {**case, "news": case["news"][-max_fetch:]}
    for article in case["news"]:
        if load_cached_article(article["id"]) is None:
            save_article(fetch(article))
    enriched = with_article_text(case)
    usable = [a for a in enriched["news"] if a.get("article_text") and a.get("article_published_at")]
    return {**enriched, "news": usable[-max_articles:]}, len(case["news"])


def summarize(result, news, considered):
    by_id = {a["id"]: a for a in news}
    contributions = sorted(result.get("contributions", []), key=lambda c: abs(c["contribution"]), reverse=True)
    evidence = []
    for item in contributions[:5]:
        article = by_id.get(item["article_id"], {})
        evidence.append({"title": article.get("title"), "source": article.get("source"),
                         "date": article.get("date"), "url": article.get("article_url") or article.get("url"),
                         "contribution": item["contribution"]})
    return {"status": "SCORED", "direction": result["direction"], "pressure": result["score"],
            "articles_considered": considered, "articles_judged": len(result.get("events", [])),
            "rubric_version": result.get("rubric_version"), "model": result.get("model"), "evidence": evidence}


def judge_item(name, case, considered, judge, store, empty_status):
    base = {"as_of_month": case["as_of_month"], "target_month": case["target_month"]}
    if not case["news"]:
        return {**base, "status": empty_status, "direction": None, "pressure": None,
                "articles_considered": considered, "articles_judged": 0, "evidence": []}
    try:
        result = judge(case)
    except Exception as exc:  # one category failing must not drop the other
        log.error("%s judge failed for %s: %s: %s", name, case["case_id"], type(exc).__name__, exc)
        return {**base, "status": "ERROR", "direction": None, "pressure": None,
                "articles_considered": considered, "articles_judged": 0, "evidence": []}
    store.save(result)
    return {**base, **summarize(result, case["news"], considered)}


def run_daily(settings, month=None, max_ram_headlines=None, max_gpu_articles=8,
              chat_judge=None, jev_judge=None, fetch=fetch_article, now=None):
    rows = load_feed(news_feed_path(settings))
    month = month or latest_month(rows)
    ram = ram_case(rows, month, max_ram_headlines or settings.max_articles)
    gpu, gpu_considered = gpu_case(settings, month, max_gpu_articles, fetch)
    chat_judge = chat_judge or OpenRouterJudge(settings.openrouter_api_key, settings.openrouter_model)
    jev_judge = jev_judge or GpuJevJudge(settings.openrouter_api_key)
    items = {
        "DDR5": judge_item("DDR5", ram, len(ram["news"]), chat_judge.evaluate_rubric,
                           JudgmentStore(settings.db_path, "rubric_judgments_v2"), "NO_NEWS"),
        "GPU": judge_item("GPU", gpu, gpu_considered, jev_judge.evaluate,
                          JudgmentStore(settings.db_path, "ohm_gpu_jev_judgments_v1"), "NO_TEXT"),
    }
    return {"schema_version": SCHEMA_VERSION,
            "generated_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
            "news_month": month, "items": items, "limitations": LIMITATIONS}


def write_atomic(payload, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".judge-", suffix=".json")
    with os.fdopen(fd, "w") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
    os.replace(tmp, path)
    return path


def default_output():
    return Path(os.environ.get("JUDGE_OUTPUT", OUTPUT_DIR / "judge.json"))
