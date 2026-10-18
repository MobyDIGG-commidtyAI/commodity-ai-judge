# DDR5 price-pressure rubric (v2)

This document describes the **implemented** rubric in `src/hardware_signal/rubric.py`. Its goal is to turn dated hardware-news headlines into an inspectable, monthly directional signal for the **next month's DDR5 retail price index**. The LLM assigns event attributes; deterministic Python code combines them. The result is a research signal, not a price forecast, probability of a price increase, or trading instruction.

## What the judge sees

For one `case_id` such as `ddr5-2026-02`, the original rubric judge receives the case month, target month, and up to 20 RAM news records from that case month. Each record has an ID, date, title, source, and URL. The rubric request **does not include price history**: it asks the model to extract news events, while Python handles aggregation and later comparison with the index. The original `rubric-case` path uses titles only. The separate `article-rubric-case` path uses cached source article bodies.

`cases.py` selects headlines in date and ID order. `openrouter.py` sends the rubric system prompt and case news to the model specified by `OPENROUTER_MODEL` at temperature 0. The model must return one event object per supplied headline, including irrelevant ones. `validate_rubric()` rejects missing, duplicate, out-of-range, or unsupported event records. If validation fails, no rubric result is stored.

## The eight dimensions

All signs refer to the **DDR5 retail price**, not a manufacturer's stock price or the sentiment of a headline.

### DIM-1: Supply impact (`supply_impact`, integer -2 to +2)

Measures the expected change in available DDR5 supply. **Positive means less supply and upward price pressure**; negative means more supply and downward pressure. A confirmed wafer-start reduction can score positive even if the same article reports poor earnings. This is the sentiment-inversion problem: negative company news need not mean falling product prices. A capacity addition can score negative if the headline supports a DDR5 supply increase. Zero means the title does not establish a DDR5 supply effect. The model must avoid treating HBM, DDR4, or NAND capacity as DDR5 supply without a stated shared-capacity link.

The distinction between supply and demand shocks is inspired by [Kilian (2009)](https://ftp.aeaweb.org/articles?id=10.1257%2Faer.99.3.1053). His oil-market identification method is **not** reproduced here; our score is a headline annotation.

### DIM-2: Demand impact (`demand_impact`, integer -2 to +2)

Measures the expected change in DDR5 buying pressure. Positive means stronger demand and upward price pressure; negative means weaker demand and downward pressure. Relevant examples include server or PC memory procurement, cancellations, or inventory replenishment when the title supports a DDR5 connection. Demand is scored separately from supply so opposing forces can offset each other. General AI enthusiasm, a rising chipmaker share price, or growth in an unrelated memory product does not by itself establish DDR5 demand.

### DIM-3: Physical production disruption (`production_disruption`, integer 0 to 4)

Measures **unplanned physical interruption**, from 0 (none), 1 (brief localized problem), 2 (material plant interruption), 3 (major multi-day outage), to 4 (severe multi-site or prolonged loss). Power failures, contamination, or earthquake-related fab downtime could qualify when supported by the headline. A planned production cut, delayed investment, or routine capacity allocation is **not** a physical disruption: record its supply effect in DIM-1 instead. This distinction is motivated by the disruption literature of [Hendricks and Singhal (2005)](https://onlinelibrary.wiley.com/doi/pdf/10.1111/j.1937-5956.2005.tb00008.x); their stock-return estimates are not transferred into this DDR5 score.

### DIM-4: Market scope (`market_scope`, integer 0 to 4)

Records the reach of the **DDR5-relevant effect**, not merely the geography in the headline: 0 = irrelevant to DDR5, 1 = one company, 2 = one product segment, 3 = the DRAM industry, 4 = the global semiconductor supply chain. The score multiplier is `market_scope / 4`, so scope 0 removes the event's contribution. The 0-4 market scale is our adaptation of event-scope thinking from [ACE event annotation](https://www.ldc.upenn.edu/sites/www.ldc.upenn.edu/files/english-events-guidelines-v5.4.3.pdf); it is not an ACE numeric standard. A worldwide HBM announcement still gets no DDR5 impact unless its transmission to DDR5 is supported.

### DIM-5: Duration horizon (`duration_horizon`, integer 0 to 4)

Describes expected persistence: 0 = under one week, 1 = one week to under one month, 2 = one to three months, 3 = over three to twelve months, 4 = over one year. The implementation maps these classes to **assumed** half-lives of 0.125, 0.5, 2, 6, and 18 months. Because the target is next month, short-lived events decay sharply before that horizon. Temporal event annotation and news-aware forecasting motivate this field, including [*From News to Forecast*](https://arxiv.org/abs/2409.17515); that paper does not supply our half-life values.

### DIM-6: Event category (`event_category`, one of 15 classes)

The allowed classes are `production_cut`, `capacity_addition`, `plant_outage`, `oversupply`, `demand_growth`, `demand_decline`, `inventory_drawdown`, `inventory_build`, `contract_price_increase`, `contract_price_decrease`, `hbm_capacity_shift`, `product_eol`, `export_control`, `trade_dispute`, and `other`. The category is an **audit and future feature**: it does not directly multiply the current score. A category label does not replace DIM-1 or DIM-2; for example, `hbm_capacity_shift` alone does not prove DDR5 supply contraction. The taxonomy adapts market terms used in [TrendForce DRAM research](https://www.trendforce.com/research/dram). It is not a licensed RavenPack taxonomy implementation.

### DIM-7: Event certainty (`event_certainty`, number 0 to 1)

Measures whether the described event happened or is credibly expected to happen. A rumor receives a low value; a reported plan can be intermediate; a completed or officially confirmed event can be high. The number multiplies the event score. It does **not** measure the size of the DDR5 price effect. A confirmed company announcement can have high event certainty even when its supply magnitude is unclear. This separation is inspired by [FactBank](https://catalog.ldc.upenn.edu/docs/LDC2009T23/readme.pdf), which annotates event factuality. No mapping from FactBank labels to these numbers is claimed.

### DIM-8: Impact confidence (`impact_confidence`, number 0 to 1)

Measures how strongly the **supplied source text** supports the assigned DDR5 impact and its magnitude. A quantified, directly DDR5-relevant statement can receive more weight than an unquantified or indirect memory-market report. The number multiplies the score independently of DIM-7. For example, a company may definitely announce a production plan (`event_certainty` high), while the source leaves its DDR5 capacity effect unknown (`impact_confidence` low). A nonzero impact requires a nonempty exact phrase from the supplied title or article body in `evidence`; a zero-impact event must have zero impact confidence. This is an evidence-grounding design choice related to ideas in [RAGAS](https://arxiv.org/abs/2309.15217), not a computed RAGAS metric.

## From event scores to a monthly signal

For each event, Python first converts physical disruption to a tentative supply pressure of `production_disruption / 2`. If `supply_impact` is nonnegative, it uses the **larger** of supply impact and disruption pressure to avoid counting the same shortage twice. If supply impact is negative, it adds disruption pressure, allowing simultaneous expansion and outage effects to offset. It then adds demand impact:

```text
base = supply_component + demand_impact
half_life = (0.125, 0.5, 2, 6, 18)[duration_horizon]  # months
weight = (market_scope / 4) * event_certainty * impact_confidence
         * exp(-ln(2) / half_life)
contribution = base * weight
monthly_score = sum(contribution for every headline)
```

The signal is `UP` for a score of at least +0.5, `DOWN` for at most -0.5, and `FLAT` otherwise. Here `FLAT` means **abstain for insufficient net evidence**, not a forecast that the index will be exactly unchanged. Contributions and the total score are stored alongside every event score. Category and quoted evidence are retained for inspection but do not directly change the numeric total.

**Illustrative calculation:** suppose a hypothetical, directly relevant supply-shortage headline scores supply `+2`, demand `0`, disruption `0`, scope `4`, horizon `2`, certainty `1.0`, and impact confidence `0.8`. Its one-month contribution is `2 × 1 × 1 × 0.8 × exp(-ln(2)/2) ≈ +1.13`; by itself it crosses the `UP` threshold. This is a demonstration of the formula, **not** an observation from the dataset.

The scoring weights, half-lives, and ±0.5 thresholds are prototype policy choices. None are coefficients estimated by the cited papers. Multiple headlines about the same event currently add separately; deduplication or event clustering would be necessary before interpreting score magnitude across heavily covered months.

## Where results go and how they are checked

Run `PYTHONPATH=src python -m hardware_signal.cli rubric-case ddr5-2026-02` from the project root inside its Conda environment. This makes one OpenRouter request, validates the rubric, computes the deterministic score, and saves the result to the `rubric_judgments_v2` SQLite table under `output/judgments.sqlite3`. The record includes `rubric_version`, model ID, response ID, each event, each contribution, total score, and direction. Earlier simple-judge and rubric-v1 records remain in separate tables.

Run `PYTHONPATH=src python -m hardware_signal.cli rubric-evaluate` to compare saved directions with the next month's DDR5 index. Evaluation reports the number of judged cases, the number of `UP`/`DOWN` predictions, abstentions, coverage, and directional accuracy **among predictions**. When every case abstains, accuracy is `null`; it is not zero. A correct direction does not imply a calibrated probability, useful price magnitude forecast, or tradeable return.

## Data and interpretation limits

### Article-aware variant

`fetch-articles --case-id ID` fetches linked pages, extracts `<article>` paragraphs and publication metadata, and caches them in `output/article_cache/`. A cached body is eligible only when its publication month is no later than the case month. `article-rubric-case ID` sends only records with eligible body text to the model, uses the same eight dimensions and deterministic score, and stores the result in `article_rubric_judgments_v1`. Exact evidence may come from the title or body. `article-rubric-evaluate` evaluates those saved cases separately from the title-only rubric. Fetched page content is untrusted evidence; instructions inside it have no authority over the judge.

The current one-year window has 36 selected RAM records. Only one has a recoverable original article URL; 35 lack URLs in the underlying source data. The one fetched report, dated August 2026, contains 882 extracted words. The article-aware judge therefore has only one judged month, and its `FLAT` output gives 0 directional predictions. This is insufficient to say whether article text improves the model. Rebuilding the cohort from an article feed with stable URLs and publication timestamps is necessary before a full-year comparison.

### Jev decision-model variant

`jev-article-case ID` uses TypeSafe Jev 1.14 via OpenRouter's Decisions API. It asks eight typed questions about each full article: six fixed-choice rubric fields and two yes/no probabilities for event certainty and direct DDR5 impact support. Python maps those answers into the same scoring formula and stores the raw probability distributions in `jev_article_judgments_v1`. `jev-article-evaluate` reads that table. Jev does not generate evidence spans; `evidence` is `null`, so its output is less directly auditable than the LLM rubric. The yes/no probabilities are proxies for the original continuous certainty and confidence fields, and this Jev score should be treated as a separate rubric version rather than directly interchangeable with the LLM score.

In the current single-article test Jev assigned no supported DDR5 supply or demand effect and returned `FLAT` with score `0.0`. The next-month index rose 11.25%, but with zero directional predictions the directional accuracy is undefined.

The input dataset is a later snapshot, and its historical MemRadar index has survivorship bias. We have not verified when each index value became available, so this is not a point-in-time backtest. The original rubric uses titles only; the article-aware variant has sparse coverage. The first 20 RAM records are selected by date, not economic importance. These limits can create abstentions or misleading results even if the rubric is applied consistently.
