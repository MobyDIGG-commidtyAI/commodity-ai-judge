import unittest

from hardware_signal.config import Settings
from hardware_signal.gpu import build_gpu_cases, build_ohm_gpu_cases, load_gpu_prices
from dataset import requires_dataset


@requires_dataset
class GpuCaseTest(unittest.TestCase):
    def test_gpu_case_uses_consumer_index_and_gpu_news(self):
        settings = Settings.from_env()
        cases = build_gpu_cases(settings)
        case = next(c for c in cases if c["case_id"] == "gpu-2026-08")
        self.assertEqual(case["target_month"], "2026-09")
        self.assertEqual(case["news"][0]["id"], "article-2975")
        prices = load_gpu_prices(settings.data_dir)
        self.assertLess(prices["2026-09"], prices["2026-08"])

    def test_ohm_cases_use_linked_gpu_records(self):
        cases = build_ohm_gpu_cases(Settings.from_env())
        april = next(c for c in cases if c["case_id"] == "ohm-gpu-2026-04")
        self.assertEqual(april["target_month"], "2026-05")
        self.assertTrue(all(a["url"] for a in april["news"]))
        self.assertIn("ohm-3131", {a["id"] for a in april["news"]})

    def test_ohm_pending_case_is_kept_without_future_price(self):
        cases = build_ohm_gpu_cases(Settings.from_env(), include_pending=True)
        october = next(c for c in cases if c["case_id"] == "ohm-gpu-2026-10")
        self.assertEqual(october["target_month"], "2026-11")
        self.assertTrue(october["news"])


if __name__ == "__main__":
    unittest.main()
