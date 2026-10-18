import unittest

from hardware_signal.cases import build_cases
from hardware_signal.config import Settings
from hardware_signal.rubric import aggregate, validate_rubric
from dataset import requires_dataset


@requires_dataset
class RubricTest(unittest.TestCase):
    def test_supply_expansion_and_shortage_have_opposite_signs(self):
        case = build_cases(Settings.from_env())[0]
        article = case["news"][0]
        base = {"article_id": article["id"], "supply_impact": -2,
                "demand_impact": 0, "production_disruption": 0,
                "market_scope": 4, "duration_horizon": 3,
                "event_category": "production_cut", "event_certainty": 1,
                "impact_confidence": 1, "evidence": article["title"]}
        one_case = {**case, "news": [article]}
        validate_rubric(one_case, {"events": [base]})
        self.assertEqual(aggregate(one_case, [base])["direction"], "DOWN")
        shortage = {**base, "supply_impact": 2}
        self.assertEqual(aggregate(one_case, [shortage])["direction"], "UP")

    def test_missing_or_unsupported_evidence_rejected(self):
        case = build_cases(Settings.from_env())[0]
        with self.assertRaises(ValueError):
            validate_rubric(case, {"events": []})


if __name__ == "__main__":
    unittest.main()
