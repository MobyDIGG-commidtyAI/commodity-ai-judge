import unittest

from hardware_signal.cases import build_cases, load_prices
from hardware_signal.config import Settings
from hardware_signal.price_context import build_price_context
from dataset import requires_dataset


@requires_dataset
class PriceContextTest(unittest.TestCase):
    def test_context_uses_only_as_of_prices(self):
        settings = Settings.from_env()
        case = next(row for row in build_cases(settings) if row["case_id"] == "ddr5-2025-10")
        context = case["price_context"]
        prices = load_prices(settings.data_dir)
        self.assertEqual(context["current_index"], prices["2025-10"])
        self.assertAlmostEqual(context["return_1m"], prices["2025-10"] / prices["2025-09"] - 1)
        self.assertNotIn("2025-11", str(context))

    def test_price_level_alone_does_not_emit_direction(self):
        context = build_price_context([{"month": "2025-01", "index": 100},
                                       {"month": "2025-02", "index": 110},
                                       {"month": "2025-03", "index": 130}])
        self.assertGreater(context["distance_from_6m_mean"], 0)
        self.assertNotIn("direction", context)


if __name__ == "__main__":
    unittest.main()
