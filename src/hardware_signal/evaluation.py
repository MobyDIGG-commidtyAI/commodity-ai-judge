from .cases import load_prices


def evaluate(cases, judgments, data_dir, abstain_flat=False):
    by_id = {case["case_id"]: case for case in cases}
    prices = load_prices(data_dir)
    rows = []
    for judgment in judgments:
        case = by_id.get(judgment["case_id"])
        if case is None:
            continue
        change = prices[case["target_month"]] / prices[case["as_of_month"]] - 1
        actual = "UP" if change > 0 else "DOWN" if change < 0 else "FLAT"
        rows.append({"case_id": case["case_id"], "prediction": judgment["direction"],
                     "actual": actual, "actual_index_change": change,
                     "correct": judgment["direction"] == actual})
    active = [row for row in rows if row["prediction"] != "FLAT"] if abstain_flat else rows
    result = {"count": len(rows), "accuracy": sum(row["correct"] for row in active) / len(active) if active else None,
              "rows": rows}
    if abstain_flat:
        result.update({"predicted_count": len(active), "abstained_count": len(rows) - len(active),
                       "coverage": len(active) / len(rows) if rows else None})
    return result
