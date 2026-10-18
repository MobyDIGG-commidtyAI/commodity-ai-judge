# Price context for the DDR5 judge

## Why add it

The news rubric describes potential supply and demand pressure. A next-month price move can also depend on what the index has **already done**: the same news may confirm an ongoing rise, or much of its effect may already be reflected in the current price. A high current index is not, by itself, evidence of a fall. Recent price changes can be consistent with either momentum or reversal. The hybrid judge receives both views and must explain its decision.

This stage leaves the eight news-event dimensions unchanged. It is a separate comparison against the news-only rubric, not a claim that the hybrid is more accurate.

## As-of features

`price_context.py` computes features from monthly index observations ending at `as_of_month`. It never reads the target month's value. With current index `P_t`:

| Field | Calculation | Interpretation |
| --- | --- | --- |
| `current_index` | `P_t` | Latest index level |
| `return_1m` | `P_t/P_(t-1) - 1` | Most recent monthly move |
| `return_3m` | `P_t/P_(t-3) - 1` | Three-month cumulative move |
| `return_6m` | `P_t/P_(t-6) - 1` | Six-month cumulative move |
| `trailing_6m_mean` | Mean of the last six index levels, including `P_t` | Recent reference level |
| `distance_from_6m_mean` | `P_t/mean - 1` | Relative stretch above or below that mean |
| `zscore_6m` | `(P_t-mean)/population_sd` over those six levels | Stretch in recent standard-deviation units |
| `drawdown_from_6m_high` | `P_t/max(last six levels) - 1` | Distance below recent high |
| `months_available` | Number of past months supplied, at most 12 | History sufficiency |

Unavailable lagged returns and unstable statistics are `null`; the code does not fill them with future values or zero. The feature builder emits **no direction**. The hybrid OpenRouter judge receives these features plus the saved rubric's direction, score, event attributes, contributions, and headlines. It returns `UP`, `DOWN`, or abstain (`FLAT`), confidence, an explanation, evidence IDs, and a price-regime label (`momentum`, `stretched`, `neutral`, or `insufficient_history`). The regime label is descriptive; no deterministic threshold maps it to a direction.

## How to run

Use the project-local Conda environment and run from the project root:

```sh
PYTHONPATH=src python -m hardware_signal.cli price-context ddr5-2025-10
PYTHONPATH=src python -m hardware_signal.cli rubric-case ddr5-2025-10
PYTHONPATH=src python -m hardware_signal.cli hybrid-case ddr5-2025-10
PYTHONPATH=src python -m hardware_signal.cli hybrid-evaluate
```

`hybrid-case` makes one additional OpenRouter request and requires an existing rubric-v2 result for that case. It saves to `hybrid_judgments_v1`, leaving simple-judge and rubric-only records intact. `hybrid-evaluate` reports coverage and accuracy among non-abstained predictions. Compare the three methods on the **same months**; fit any decision thresholds on earlier months and evaluate on later months.

## Limits

The index is a retail benchmark, not a traded asset. The archived historical series has survivorship bias, and its publication timing has not been verified. Even though features use only months up to `as_of_month` in the file, this is not yet a point-in-time backtest. The dataset has only a few dozen monthly observations, so a high `zscore_6m` is a local description, not a calibrated probability of reversal. Research on commodity prices finds both momentum and mean-reversion patterns depending on the market and instrument; neither should be assumed for this DDR5 retail index without an out-of-sample test. [Commodity spot and futures study](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2833003), [time-series validation guidance](https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html).
