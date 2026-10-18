import argparse
import json
from pathlib import Path

from .api import serve
from .article_cache import (download_page_snapshot, extract_article_snapshot, fetch_article, save_article,
                            load_cached_article, with_article_text)
from .cases import build_cases
from .config import ROOT, Settings
from .evaluation import evaluate
from .gpu import GpuJevJudge, build_gpu_cases, build_ohm_gpu_cases, load_gpu_prices
from .judge import validate_judgment
from .jev import JevJudge
from .openrouter import OpenRouterJudge
from .storage import JudgmentStore


def main():
    parser = argparse.ArgumentParser(description="Hardware price judge service")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve")
    export = sub.add_parser("export-cases")
    export.add_argument("--output", type=Path, default=ROOT / "output/judge_cases.jsonl")
    ingest = sub.add_parser("import-judgments")
    ingest.add_argument("path", type=Path)
    sub.add_parser("evaluate")
    judge = sub.add_parser("judge-case", help="Call OpenRouter for one case and store its judgment")
    judge.add_argument("case_id")
    rubric = sub.add_parser("rubric-case", help="Apply eight-dimension rubric to one case")
    rubric.add_argument("case_id")
    sub.add_parser("rubric-evaluate")
    hybrid = sub.add_parser("hybrid-case", help="Combine an existing rubric with lagged price context")
    hybrid.add_argument("case_id")
    sub.add_parser("hybrid-evaluate")
    context = sub.add_parser("price-context", help="Show known price context for one case")
    context.add_argument("case_id")
    fetch = sub.add_parser("fetch-articles", help="Cache linked article bodies")
    selection = fetch.add_mutually_exclusive_group(required=True)
    selection.add_argument("--case-id")
    selection.add_argument("--latest-year", action="store_true")
    article_rubric = sub.add_parser("article-rubric-case", help="Score cached article text and titles")
    article_rubric.add_argument("case_id")
    sub.add_parser("article-rubric-evaluate")
    jev = sub.add_parser("jev-article-case", help="Score cached article text with TypeSafe Jev")
    jev.add_argument("case_id")
    sub.add_parser("jev-article-evaluate")
    gpu_fetch = sub.add_parser("gpu-fetch-articles", help="Cache linked consumer GPU articles")
    gpu_fetch.add_argument("--latest-year", action="store_true", required=True)
    gpu_jev = sub.add_parser("gpu-jev-case", help="Score a GPU case using full articles and Jev")
    gpu_jev.add_argument("case_id")
    sub.add_parser("gpu-jev-evaluate")
    ohm = sub.add_parser("ohm-gpu-jev-case", help="Score dated OHM GPU full articles with Jev")
    ohm.add_argument("case_id")
    ohm_eval = sub.add_parser("ohm-gpu-jev-evaluate")
    ohm_eval.add_argument("--all-history", action="store_true",
                          help="Report May 2024 through the latest OHM news month, including pending outcomes")
    ohm_fetch = sub.add_parser("ohm-gpu-fetch-articles", help="Cache OHM GPU source pages")
    ohm_fetch_selection = ohm_fetch.add_mutually_exclusive_group(required=True)
    ohm_fetch_selection.add_argument("--latest-year", action="store_true")
    ohm_fetch_selection.add_argument("--all-history", action="store_true")
    ohm_download = sub.add_parser("ohm-gpu-download-pages", help="Save raw linked OHM GPU HTML pages")
    ohm_download_selection = ohm_download.add_mutually_exclusive_group(required=True)
    ohm_download_selection.add_argument("--latest-year", action="store_true")
    ohm_download_selection.add_argument("--all-history", action="store_true")
    daily = sub.add_parser("daily", help="Judge this month's DDR5 and GPU news and write judge.json for the API")
    daily.add_argument("--month", help="News month YYYY-MM (default: latest month in the news feed)")
    daily.add_argument("--output", type=Path, help="Output path (default: JUDGE_OUTPUT or OUTPUT_DIR/judge.json)")
    daily.add_argument("--max-gpu-articles", type=int, default=8, help="Cap on Jev calls for GPU articles")
    args = parser.parse_args()
    settings = Settings.from_env()
    if args.command == "daily":
        import logging
        from .daily import default_output, run_daily, write_atomic
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
        payload = run_daily(settings, month=args.month, max_gpu_articles=args.max_gpu_articles)
        path = write_atomic(payload, args.output or default_output())
        print(json.dumps({"output": str(path), "news_month": payload["news_month"],
                          "items": {k: {f: v[f] for f in ("status", "direction", "pressure", "articles_judged")}
                                    for k, v in payload["items"].items()}}, indent=2))
        # exit 3 when a category could not be judged, so the job execution shows the failure
        raise SystemExit(3 if any(v["status"] == "ERROR" for v in payload["items"].values()) else 0)
    if args.command == "serve":
        serve(settings)
    elif args.command == "export-cases":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        cases = build_cases(settings)
        with args.output.open("w") as handle:
            for case in cases:
                handle.write(json.dumps(case, ensure_ascii=False) + "\n")
        print(f"Exported {len(cases)} cases to {args.output}")
    elif args.command == "import-judgments":
        by_id = {case["case_id"]: case for case in build_cases(settings)}
        store = JudgmentStore(settings.db_path)
        count = 0
        with args.path.open() as handle:
            for number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                raw = json.loads(line)
                case = by_id.get(raw.get("case_id"))
                if case is None:
                    raise ValueError(f"line {number}: unknown case_id")
                store.save(validate_judgment(case, raw))
                count += 1
        print(f"Imported {count} judgments")
    elif args.command == "fetch-articles":
        cases = build_cases(settings)
        if args.case_id:
            cases = [case for case in cases if case["case_id"] == args.case_id]
            if not cases:
                parser.error(f"unknown case_id: {args.case_id}")
        else:
            latest_target = max(case["target_month"] for case in cases)
            cases = [case for case in cases if
                     (int(latest_target[:4]) * 12 + int(latest_target[5:]) -
                      int(case["target_month"][:4]) * 12 - int(case["target_month"][5:])) < 12]
        articles = {article["id"]: article for case in cases for article in case["news"]}
        counts = {}
        for article in articles.values():
            result = fetch_article(article)
            save_article(result)
            counts[result["status"]] = counts.get(result["status"], 0) + 1
        print(json.dumps({"articles": len(articles), "status_counts": counts}, indent=2))
    elif args.command == "gpu-fetch-articles":
        cases = build_gpu_cases(settings)
        latest = max(c["target_month"] for c in cases)
        ordinal = lambda month: int(month[:4]) * 12 + int(month[5:])
        selected = [c for c in cases if ordinal(latest) - ordinal(c["target_month"]) < 12]
        articles = {a["id"]: a for c in selected for a in c["news"]}
        counts = {}
        for article in articles.values():
            result = fetch_article(article)
            save_article(result)
            counts[result["status"]] = counts.get(result["status"], 0) + 1
        print(json.dumps({"articles": len(articles), "status_counts": counts}, indent=2))
    elif args.command == "ohm-gpu-fetch-articles":
        cases = build_ohm_gpu_cases(settings, include_pending=args.all_history)
        if args.all_history:
            selected = [c for c in cases if c["as_of_month"] >= "2024-05"]
        else:
            latest = max(c["target_month"] for c in cases)
            ordinal = lambda month: int(month[:4]) * 12 + int(month[5:])
            selected = [c for c in cases if ordinal(latest) - ordinal(c["target_month"]) < 12]
        articles = {a["id"]: a for c in selected for a in c["news"]}
        counts = {}
        from .article_cache import SNAPSHOT_DIR
        for article in articles.values():
            snapshot = SNAPSHOT_DIR / f"{article['id']}.html"
            result = (extract_article_snapshot(article) if snapshot.exists() else
                      (load_cached_article(article["id"]) or fetch_article(article)))
            save_article(result)
            counts[result["status"]] = counts.get(result["status"], 0) + 1
        print(json.dumps({"articles": len(articles), "status_counts": counts}, indent=2))
    elif args.command == "ohm-gpu-download-pages":
        cases = build_ohm_gpu_cases(settings, include_pending=args.all_history)
        if args.all_history:
            selected = [c for c in cases if c["as_of_month"] >= "2024-05"]
        else:
            latest = max(c["target_month"] for c in cases)
            ordinal = lambda month: int(month[:4]) * 12 + int(month[5:])
            selected = [c for c in cases if ordinal(latest) - ordinal(c["target_month"]) < 12]
        articles = {a["id"]: a for c in selected for a in c["news"]}
        from .article_cache import SNAPSHOT_DIR
        results = []
        for article in articles.values():
            snapshot = SNAPSHOT_DIR / f"{article['id']}.html"
            if snapshot.exists():
                results.append({"article_id": article["id"], "status": "already_saved",
                                "snapshot_path": str(snapshot), "bytes": snapshot.stat().st_size})
            else:
                results.append(download_page_snapshot(article))
        report = ROOT / ("output/ohm_gpu_page_downloads_all_history.json" if args.all_history else
                         "output/ohm_gpu_page_downloads.json")
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(results, indent=2))
        counts = {}
        for result in results:
            counts[result["status"]] = counts.get(result["status"], 0) + 1
        print(json.dumps({"pages": len(results), "status_counts": counts,
                          "report": str(report)}, indent=2))
    elif args.command == "gpu-jev-case":
        cases = {c["case_id"]: c for c in build_gpu_cases(settings)}
        if args.case_id not in cases:
            parser.error(f"unknown case_id: {args.case_id}")
        result = GpuJevJudge(settings.openrouter_api_key).evaluate(with_article_text(cases[args.case_id]))
        JudgmentStore(settings.db_path, "gpu_jev_article_judgments_v1").save(result)
        print(json.dumps(result, indent=2))
    elif args.command == "gpu-jev-evaluate":
        rows = []
        cases = {c["case_id"]: c for c in build_gpu_cases(settings)}
        prices = load_gpu_prices(settings.data_dir)
        for judgment in JudgmentStore(settings.db_path, "gpu_jev_article_judgments_v1").all():
            case = cases.get(judgment["case_id"])
            if case is None:
                continue
            change = prices[case["target_month"]] / prices[case["as_of_month"]] - 1
            actual = "UP" if change > 0 else "DOWN" if change < 0 else "FLAT"
            rows.append({"case_id": case["case_id"], "prediction": judgment["direction"],
                         "actual": actual, "actual_index_change": change,
                         "correct": judgment["direction"] == actual})
        active = [row for row in rows if row["prediction"] != "FLAT"]
        print(json.dumps({"count": len(rows), "predicted_count": len(active),
                          "abstained_count": len(rows)-len(active),
                          "coverage": len(active)/len(rows) if rows else None,
                          "accuracy": sum(r["correct"] for r in active)/len(active) if active else None,
                          "rows": rows}, indent=2))
    elif args.command == "ohm-gpu-jev-case":
        cases = {c["case_id"]: c for c in build_ohm_gpu_cases(settings)}
        if args.case_id not in cases:
            parser.error(f"unknown case_id: {args.case_id}")
        enriched = with_article_text(cases[args.case_id])
        enriched["news"] = [a for a in enriched["news"] if a.get("article_text") and a.get("article_published_at")]
        result = GpuJevJudge(settings.openrouter_api_key).evaluate(enriched)
        result["dataset"] = "ohm/news_feed.csv"
        JudgmentStore(settings.db_path, "ohm_gpu_jev_judgments_v1").save(result)
        print(json.dumps(result, indent=2))
    elif args.command == "ohm-gpu-jev-evaluate":
        import csv
        cases = build_ohm_gpu_cases(settings, include_pending=args.all_history)
        prices = load_gpu_prices(settings.data_dir)
        if args.all_history:
            cohort = [c for c in cases if c["as_of_month"] >= "2024-05"]
        else:
            latest = max(c["target_month"] for c in cases)
            ordinal = lambda m: int(m[:4]) * 12 + int(m[5:])
            cohort = [c for c in cases if 0 <= ordinal(latest) - ordinal(c["target_month"]) < 12]
        judgments = {j["case_id"]: j for j in JudgmentStore(settings.db_path, "ohm_gpu_jev_judgments_v1").all()}
        rows = []
        for case in cohort:
            enriched = with_article_text(case)
            usable = sum(bool(a.get("article_text") and a.get("article_published_at")) for a in enriched["news"])
            judgment = judgments.get(case["case_id"])
            price_available = case["as_of_month"] in prices and case["target_month"] in prices
            change = (prices[case["target_month"]] / prices[case["as_of_month"]] - 1) if price_available else None
            judged_articles = len(judgment.get("events", [])) if judgment else 0
            pressure_status = ("NO_URL" if not case["news"] else
                               "NO_TEXT" if usable == 0 else
                               "NOT_JUDGED" if not judgment else
                               "PARTIAL" if judged_articles < usable else "SCORED")
            rows.append({"case_month": case["as_of_month"], "target_month": case["target_month"],
                         "linked_records": len(case["news"]), "readable_articles": usable,
                         "judged_articles": judged_articles, "pressure_status": pressure_status,
                         "price_pressure_score": judgment["score"] if judgment else "",
                         "actual_change_pct": round(change * 100, 2) if price_available else "",
                         "price_status": "OBSERVED" if price_available else "PENDING"})
        path = ROOT / ("output/ohm_gpu_price_pressure_2024-05_to_2026-10.csv" if args.all_history else
                       "output/ohm_gpu_price_pressure_2025-10_to_2026-09.csv")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        active = [r for r in rows if r["price_pressure_score"] != ""]
        print(json.dumps({"months": len(rows), "months_with_price_outcome":
                          sum(r["price_status"] == "OBSERVED" for r in rows),
                          "linked_records": sum(r["linked_records"] for r in rows),
                          "months_with_readable_articles": sum(r["readable_articles"] > 0 for r in rows),
                          "months_with_pressure_score": len(active),
                          "report": str(path), "rows": rows}, indent=2))
    elif args.command in ("judge-case", "rubric-case", "hybrid-case", "price-context", "article-rubric-case", "jev-article-case"):
        cases = {case["case_id"]: case for case in build_cases(settings)}
        if args.case_id not in cases:
            parser.error(f"unknown case_id: {args.case_id}")
        if args.command == "price-context":
            print(json.dumps(cases[args.case_id]["price_context"], indent=2))
            return
        if args.command == "jev-article-case":
            article_case = with_article_text(cases[args.case_id])
            result = JevJudge(settings.openrouter_api_key).evaluate(article_case)
            JudgmentStore(settings.db_path, "jev_article_judgments_v1").save(result)
            print(json.dumps(result, indent=2))
            return
        provider = OpenRouterJudge(settings.openrouter_api_key, settings.openrouter_model)
        if args.command == "rubric-case":
            result = provider.evaluate_rubric(cases[args.case_id])
            JudgmentStore(settings.db_path, "rubric_judgments_v2").save(result)
        elif args.command == "article-rubric-case":
            article_case = with_article_text(cases[args.case_id])
            result = provider.evaluate_article_rubric(article_case)
            JudgmentStore(settings.db_path, "article_rubric_judgments_v1").save(result)
        else:
            if args.command == "hybrid-case":
                rubrics = {row["case_id"]: row for row in JudgmentStore(settings.db_path, "rubric_judgments_v2").all()}
                if args.case_id not in rubrics:
                    parser.error("run rubric-case for this case before hybrid-case")
                result = provider.evaluate_hybrid(cases[args.case_id], rubrics[args.case_id])
                JudgmentStore(settings.db_path, "hybrid_judgments_v1").save(result)
            else:
                result = provider.evaluate(cases[args.case_id])
                JudgmentStore(settings.db_path).save(result)
        print(json.dumps(result, indent=2))
    else:
        table = {"rubric-evaluate": "rubric_judgments_v2", "hybrid-evaluate": "hybrid_judgments_v1",
                 "article-rubric-evaluate": "article_rubric_judgments_v1",
                 "jev-article-evaluate": "jev_article_judgments_v1"}.get(args.command, "judgments")
        result = evaluate(build_cases(settings), JudgmentStore(settings.db_path, table).all(),
                          settings.data_dir, abstain_flat=args.command in
                          ("rubric-evaluate", "hybrid-evaluate", "article-rubric-evaluate", "jev-article-evaluate"))
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
