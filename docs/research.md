# Research notes (hardware judge signal)

> Original notes from the research workspace. Generated `output/` files, the `dataset/` folders and the Conda
> environment are not part of this repo, so links into them do not resolve here.

A research service for monthly DDR5 retail price direction. It builds dated cases from `dataset/chin`, asks an OpenRouter model for an `UP` / `DOWN` / `FLAT` decision, stores judgments in SQLite, and reports next-month direction accuracy. It does not place trades.

For each rubric dimension, its evidence rule, the scoring formula, and evaluation semantics, see [the rubric guide](rubric.md).

## Layout

```text
src/hardware_signal/
  config.py       .env configuration
  cases.py        price/news loading and dated case building
  article_cache.py linked article retrieval, extraction, and local cache
  jev.py         TypeSafe Jev Decisions API article rubric
  gpu.py         consumer GPU retail-index cases and GPU Jev questions
  judge.py        judge contract and output validation
  openrouter.py   OpenRouter Chat Completions adapter
  rubric.py       eight-dimension event schema and signal aggregation
  price_context.py lagged price and relative-level features
  storage.py      SQLite judgment persistence
  evaluation.py   next-month direction scoring
  api.py          HTTP endpoints
  cli.py          service and batch commands
dataset/chin/     existing source data
output/           generated files and database
.env.example      local configuration template
```

## Setup

Use the project-local Conda environment. It already exists in this workspace.

```sh
source "$(conda info --base)/etc/profile.d/conda.sh" && conda activate "./.conda/codex/dev"
cp .env.example .env
```

Set `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` in `.env`. The model value is the exact OpenRouter `author/model` slug you choose. Keep `.env` private; it is gitignored. No API request is made until you run `judge-case`.

No third-party runtime packages are needed. Run from the project root:

```sh
PYTHONPATH=src python -m hardware_signal.cli serve
```

Or export cases for a batch judge and import its JSONL results:

```sh
PYTHONPATH=src python -m hardware_signal.cli export-cases
PYTHONPATH=src python -m hardware_signal.cli import-judgments output/judgments.jsonl
PYTHONPATH=src python -m hardware_signal.cli evaluate
```

For the new rubric judge, score one case and inspect the eight dimensions per headline:

```sh
PYTHONPATH=src python -m hardware_signal.cli rubric-case ddr5-2026-02
PYTHONPATH=src python -m hardware_signal.cli rubric-evaluate
```

To inspect as-of price structure and ask a **separate hybrid judge** to weigh it against a saved rubric result:

```sh
PYTHONPATH=src python -m hardware_signal.cli price-context ddr5-2025-10
PYTHONPATH=src python -m hardware_signal.cli hybrid-case ddr5-2025-10
PYTHONPATH=src python -m hardware_signal.cli hybrid-evaluate
```

Run `rubric-case` for that month first. The hybrid decision is stored separately in `hybrid_judgments_v1`. See [the price-context guide](price-context.md) for the features and limits.

Rubric v2 writes to `rubric_judgments_v2`, preserving both the simple-judge results and rubric v1 experiments. `rubric-evaluate` treats `FLAT` as an abstention and reports coverage and accuracy only for `UP`/`DOWN` predictions.

### Full-article experiment

Fetch the source page before running the article judge:

```sh
PYTHONPATH=src python -m hardware_signal.cli fetch-articles --case-id ddr5-2026-08
PYTHONPATH=src python -m hardware_signal.cli article-rubric-case ddr5-2026-08
PYTHONPATH=src python -m hardware_signal.cli article-rubric-evaluate
```

`fetch-articles --latest-year` checks all cases in the latest 12-month evaluation window. It caches extracted body text, publication metadata, and source provenance in `output/article_cache/`. The article judge sends **only records with fetched article text** to OpenRouter, accepts evidence quoted from the body or title, and stores results separately in `article_rubric_judgments_v1`. Cases without an article body cannot run through this judge. The source mapping in `data/article_url_overrides.csv` links one dataset URL to its verified canonical article page.

In the current one-year cohort, only **1 of 36** selected RAM records has a recoverable original article URL; the other 35 have none. The single full article is [this Yahoo Finance report](https://finance.yahoo.com/technology/ai/articles/memory-shortage-isn-t-close-155233128.html), published in August 2026. Most missing URLs trace to the upstream Telegram-based finance-news dataset. A full-article one-year comparison requires an article source with URLs and publication timestamps for the missing months. See [the rubric guide](rubric.md) for interpretation.

To use **Jev 1.14** instead of the generative LLM for the full-article rubric:

```sh
PYTHONPATH=src python -m hardware_signal.cli jev-article-case ddr5-2026-08
PYTHONPATH=src python -m hardware_signal.cli jev-article-evaluate
```

Jev uses OpenRouter's Decisions API and the same `OPENROUTER_API_KEY`; it does not use `OPENROUTER_MODEL`. It returns typed choices and probabilities for all eight dimensions. Jev cannot generate an exact evidence quote, so its event records have `evidence: null` and preserve the complete typed answers in `jev_article_judgments_v1`. The Jev and LLM article results are separate experiments. On the one available full article, Jev scored `0.0` and abstained (`FLAT`); directional accuracy remains undefined with zero predictions.

### Consumer GPU article experiment

This separate path targets the **next-month consumer GPU retail index** (`gpuRetail` in the price contract), with GPU-specific rubric questions:

```sh
PYTHONPATH=src python -m hardware_signal.cli gpu-fetch-articles --latest-year
PYTHONPATH=src python -m hardware_signal.cli gpu-jev-case gpu-2026-08
PYTHONPATH=src python -m hardware_signal.cli gpu-jev-evaluate
```

The one-year coverage report is [gpu_jev_article_backtest_2025-10_to_2026-09.csv](../output/gpu_jev_article_backtest_2025-10_to_2026-09.csv). Only one selected GPU record in that window had a linked, extractable article: an August 2026 CNBC report about **AI server** price hikes. The GPU-specific Jev judge found no documented consumer graphics-card price effect and abstained with score `0.0`; the September 2026 consumer GPU index fell 0.77%. This gives 0 directional predictions, so directional accuracy is undefined. The report must not be treated as a full-year accuracy estimate.

The newer `dataset/ohm/news_feed.csv` adds GPU links from Hacker News. For the same consumer retail target, the OHM experiment accepts only extracted full article bodies with a publication timestamp no later than the case month:

```sh
PYTHONPATH=src python -m hardware_signal.cli ohm-gpu-fetch-articles --latest-year
PYTHONPATH=src python -m hardware_signal.cli ohm-gpu-download-pages --latest-year
PYTHONPATH=src python -m hardware_signal.cli ohm-gpu-jev-case ohm-gpu-2026-04
PYTHONPATH=src python -m hardware_signal.cli ohm-gpu-jev-case ohm-gpu-2026-05
PYTHONPATH=src python -m hardware_signal.cli ohm-gpu-jev-case ohm-gpu-2026-06
PYTHONPATH=src python -m hardware_signal.cli ohm-gpu-jev-case ohm-gpu-2026-08
PYTHONPATH=src python -m hardware_signal.cli ohm-gpu-jev-evaluate
```

The [OHM GPU report](../output/ohm_gpu_jev_article_backtest_2025-10_to_2026-09.csv) has four judged months, each with one dated article or report and a `FLAT` result. Three sources cover cloud GPU rental prices, and the fourth covers AI server systems; none establishes a consumer graphics-card retail effect. The feed has 27 linked GPU records in this one-year window. The raw-page command saved 25 HTML pages under `output/page_snapshots/` and logged the two fetch errors in `output/ohm_gpu_page_downloads.json`. Only dated article text is passed to the judge; live dashboards, discussion pages, and undated projects are excluded to avoid using current page contents as historical evidence.

For the full **May 2024–October 2026** range, use `--all-history` with the two OHM fetch commands and the evaluator:

```sh
PYTHONPATH=src python -m hardware_signal.cli ohm-gpu-download-pages --all-history
PYTHONPATH=src python -m hardware_signal.cli ohm-gpu-fetch-articles --all-history
PYTHONPATH=src python -m hardware_signal.cli ohm-gpu-jev-evaluate --all-history
```

The current [full-range GPU report](../output/ohm_gpu_price_pressure_2024-05_to_2026-10.csv) keeps the signed rubric **price-pressure score** instead of converting it to UP/DOWN/FLAT. Positive pressure suggests upward force, negative pressure downward force, and zero means the judged articles provided no supported consumer-retail pressure. A blank score means there is no stored judgment; it must not be interpreted as zero pressure. The [plot](../output/ohm_gpu_price_pressure_vs_actual.svg) displays this score separately from the next-month observed retail-index percentage change. These are different units: the pressure score is **not calibrated to a percentage price forecast**.

The report spans 30 case months; 28 have observed next-month prices. There are 125 GPU URLs, 123 saved HTML pages, and 10 pages with extracted text across 6 months. Publisher publication dates are used where available; otherwise the feed timestamp is used with `article_date_source=dataset`. Five months have stored Jev judgments, and some are partial because additional extracted articles are now available. The February 2025 consumer GPU article has pressure `+0.4633`; the next-month retail index rose 0.11%. Four other stored judgments have zero pressure because they found no supported consumer-retail effect in mostly AI server or cloud GPU articles. September and October 2026 have pending next-month price outcomes. The October news month is partial as of October 16, 2026.

### Stock-news backtest (separate target)

The `dataset/ram_gpu_stocks` track uses Nasdaq daily close prices for AMD, MU, and NVDA and downloaded publisher article text discovered via Google News RSS. It predicts each ticker's close-to-close return over the **five trading sessions beginning strictly after the article publication date**. It does not predict consumer GPU retail prices. A Jev call evaluates all saved articles assigned to one ticker and start session, producing a signed equity-pressure score. Each article body is capped at 6,000 characters in the model request; the cache records how many were truncated. A zero score means the model found no supported new equity catalyst; missing scores mean no article or no model result.

Run or resume the July–September 2026 experiment from the project root:

```sh
source "$(conda info --base)/etc/profile.d/conda.sh" && conda activate './.conda/codex/dev' && PYTHONPATH=src python scripts/backtest_stock_news.py --workers 3
```

The [case report](../output/stock_news_jev_5day_backtest_2026-07_to_09.csv), [summary](../output/stock_news_jev_5day_backtest_2026-07_to_09.json), and [pressure-versus-return plot](../output/stock_news_jev_5day_pressure_vs_return.svg) are reproducible from cached Jev responses. Of 192 ticker-session cases, 180 have complete five-session outcomes, 124 of those have scored articles, and 105 have nonzero pressure. Pressure-sign agreement is 48.6%; an always-up sign is correct 57.1% of those same 105 cases. Score/return correlation is -0.18. This exploratory result does not show predictive value. Five-session outcomes overlap, publisher pages may have been edited after their historical publication dates, Google News timestamps can be imprecise, and Nasdaq prices may be unadjusted for corporate actions.

For the latest 12 complete data months, run the same code with `--start 2025-10-01 --end 2026-09-30`. The [one-year report](../output/stock_news_jev_5day_backtest_2025-10_to_2026-09.csv) contains 753 ticker-session cases, 741 complete five-session outcomes, and 578 scored cases with observed outcomes. Among 467 nonzero-pressure cases, sign agreement is 51.0%, below the 58.9% always-up baseline on the same cases; score/return correlation is -0.07. The [monthly comparison chart](../output/stock_news_vs_ram_gpu_monthly_deltas_2025-10_to_2026-09.svg) and [values](../output/stock_news_vs_ram_gpu_monthly_deltas_2025-10_to_2026-09.csv) align stock-news pressure, stock price changes, and DDR4/DDR5/consumer-GPU retail changes by calendar month. The retail series are comparison context, not targets of this stock-news judge.

To call OpenRouter for one dated case and save the result:

```sh
PYTHONPATH=src python -m hardware_signal.cli judge-case ddr5-2025-01
PYTHONPATH=src python -m hardware_signal.cli evaluate
```

## HTTP API

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/health` | Service status |
| GET | `/cases` | Available month IDs |
| GET | `/cases/ddr5-2025-01` | Full case and judge prompts |
| POST | `/judgments` | Validate and save one judge decision |
| GET | `/judgments` | Stored decisions |
| GET | `/evaluation` | Accuracy and per-month outcomes |
| GET | `/rubric-judgments` | Event-level rubric decisions |
| GET | `/rubric-evaluation` | Rubric coverage and directional accuracy |
| GET | `/article-rubric-judgments` | Saved full-article rubric decisions |
| GET | `/article-rubric-evaluation` | Full-article coverage and directional accuracy |
| GET | `/price-context/ddr5-2025-10` | As-of lagged price features |
| GET | `/hybrid-judgments` | Combined news and price judgments |
| GET | `/hybrid-evaluation` | Combined-judge coverage and accuracy |

Example POST body (replace with an actual case ID and evidence IDs from its case):

```json
{"case_id":"ddr5-2025-01","direction":"UP","confidence":0.61,"rationale":"Supply pressure outweighs weak demand.","evidence_ids":[]}
```

## Judge behavior

`judge-case` sends the case's `system_prompt` and `user_prompt` to OpenRouter's Chat Completions API with temperature 0. The adapter validates the JSON result, adds the case ID and returned model/response ID, then saves it. An invalid response fails without saving a judgment. You can still submit a decision to `POST /judgments` or import JSONL for other providers. Keep prompt version and raw responses in separate experiment logs if you need full reproducibility.

### Rubric scoring

`rubric-case` scores every headline separately using the eight dimensions in the supplied literature note:

| Dimension | Field | Scale and meaning |
| --- | --- | --- |
| DIM-1 Supply | `supply_impact` | Integer -2..+2; positive means less DDR5 supply and upward price pressure |
| DIM-2 Demand | `demand_impact` | Integer -2..+2; positive means more DDR5 demand and upward pressure |
| DIM-3 Physical disruption | `production_disruption` | Integer 0..4; unplanned physical production interruption only |
| DIM-4 Market scope | `market_scope` | 0 irrelevant, 1 company, 2 product segment, 3 DRAM industry, 4 global semiconductor chain |
| DIM-5 Duration | `duration_horizon` | 0 under a week, 1 week to under a month, 2 one to three months, 3 over three to twelve months, 4 over a year |
| DIM-6 Event category | `event_category` | One of 15 classes defined in `rubric.py` |
| DIM-7 Event certainty | `event_certainty` | Continuous 0..1; whether the event occurred or is likely to occur |
| DIM-8 Impact confidence | `impact_confidence` | Continuous 0..1; how strongly the title supports the claimed DDR5 impact |

Nonzero impact requires an exact supporting span from the headline. Event certainty and impact confidence are separate: an official announcement can be certain while the size of its future price effect remains unclear. The model must not assume that DDR4, HBM, or NAND news directly changes DDR5 retail prices.

The prototype score per event is `(supply component + demand impact) × (market_scope/4) × event_certainty × impact_confidence × exp(-ln(2)/half_life_months)`. Production disruption contributes `production_disruption/2` to supply pressure, using the larger of the two when supply impact is already positive to avoid double counting. The half-lives for duration levels 0..4 are 0.125, 0.5, 2, 6, and 18 months. Event scores sum; at least +0.5 means `UP`, at most -0.5 means `DOWN`, and otherwise means abstain (`FLAT`). These weights and thresholds are **design hypotheses, not coefficients estimated by the cited research**; calibrate them on separate historical data before making performance claims.

The dimensions draw on these research ideas, adapted to DDR5 here: [Kilian (2009)](https://ftp.aeaweb.org/articles?id=10.1257%2Faer.99.3.1053) for separating supply and demand shocks; [Hendricks and Singhal (2005)](https://onlinelibrary.wiley.com/doi/pdf/10.1111/j.1937-5956.2005.tb00008.x) for disruption relevance; [ACE event guidelines](https://www.ldc.upenn.edu/sites/www.ldc.upenn.edu/files/english-events-guidelines-v5.4.3.pdf) and TimeML for event and temporal annotation; [From News to Forecast](https://arxiv.org/abs/2409.17515) for integrating selected news events into forecasts; [FactBank](https://catalog.ldc.upenn.edu/docs/LDC2009T23/readme.pdf) for factuality; [RAGAS](https://arxiv.org/abs/2309.15217) for evidence-grounding ideas; and [TrendForce DRAM research](https://www.trendforce.com/research/dram) for market terminology. The provided “RLCD (TypeSafe AI)” reference remains unverified, so this project does not claim to implement that method.

## Research limits

The MemRadar index comes from a later snapshot with survivorship bias, and index publication timing has not been verified. Results are prototype research, not a point-in-time trading backtest. This retail index is a benchmark rather than a tradable asset. The news file has titles and metadata, with original article links for only a subset; the first 20 RAM records per month are selected deterministically. Cached page extraction may omit paywalled or dynamically rendered content.
