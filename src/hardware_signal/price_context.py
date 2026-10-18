"""As-of monthly price features for a separate time-series judgment stage."""

from statistics import mean, pstdev


def build_price_context(history):
    """Use only observations already present in the case's price history."""
    if not history:
        raise ValueError("price history is empty")
    values = [float(row["index"]) for row in history]
    current = values[-1]
    if current <= 0 or any(value <= 0 for value in values):
        raise ValueError("price index values must be positive")

    def trailing_return(months):
        return current / values[-months - 1] - 1 if len(values) > months else None

    window = values[-6:]
    average = mean(window) if len(window) >= 3 else None
    deviation = pstdev(window) if len(window) >= 3 else None
    return {
        "as_of_month": history[-1]["month"],
        "current_index": current,
        "return_1m": trailing_return(1),
        "return_3m": trailing_return(3),
        "return_6m": trailing_return(6),
        "trailing_6m_mean": average,
        "distance_from_6m_mean": current / average - 1 if average else None,
        "zscore_6m": (current - average) / deviation if deviation else None,
        "drawdown_from_6m_high": current / max(window) - 1 if len(window) >= 3 else None,
        "months_available": len(values),
    }
