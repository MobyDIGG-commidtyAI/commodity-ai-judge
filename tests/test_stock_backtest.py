import unittest

from hardware_signal.stock_backtest import load_cases
from dataset import requires_stock_data


@requires_stock_data
class StockBacktestTest(unittest.TestCase):
    def test_full_year_window_keeps_only_requested_sessions(self):
        cases = load_cases("2025-10-01", "2026-09-30")
        self.assertEqual(len(cases), 753)
        self.assertTrue(all("2025-10-01" <= c["start_date"] <= "2026-09-30" for c in cases))
        self.assertEqual(sum(bool(c["articles"]) for c in cases), 590)

    def test_news_precedes_target_session_and_prices_follow_five_sessions(self):
        cases = load_cases()
        self.assertEqual(len(cases), 192)
        self.assertEqual({c["ticker"] for c in cases}, {"AMD", "MU", "NVDA"})
        for case in cases:
            for article, _ in case["articles"]:
                self.assertLess(article["published_utc"][:10], case["start_date"])
            if case["end_date"]:
                self.assertGreaterEqual(case["end_date"], case["start_date"])
                self.assertIsNotNone(case["actual_5day_pct"])
            else:
                self.assertIsNone(case["actual_5day_pct"])


if __name__ == "__main__":
    unittest.main()
