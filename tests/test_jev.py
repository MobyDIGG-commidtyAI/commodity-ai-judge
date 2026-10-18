import io
import json
import unittest

from hardware_signal.jev import JevJudge, QUESTIONS


class JevTest(unittest.TestCase):
    def test_typed_answers_become_separate_rubric_result(self):
        choices = {"supply_impact": "plus_1", "demand_impact": "zero",
                   "production_disruption": "0", "market_scope": "3",
                   "duration_horizon": "4", "event_category": "hbm_capacity_shift"}
        answers = {key: {"type": "choice", "choice": value} for key, value in choices.items()}
        answers.update({"event_certainty": {"type": "noul", "noul": 0.9},
                        "impact_confidence": {"type": "noul", "noul": 0.2}})
        response = {"answers": answers, "model": "typesafe/jev-1.14"}

        def transport(request, timeout):
            payload = json.loads(request.data)
            self.assertEqual(payload["model"], "typesafe/jev-1.14")
            self.assertEqual(set(payload["questions"]), set(QUESTIONS))
            return io.BytesIO(json.dumps(response).encode())

        case = {"case_id": "test", "as_of_month": "2026-08", "target_month": "2026-09",
                "news": [{"id": "a", "title": "Memory shift", "article_text": "Article body"},
                         {"id": "b", "title": "Unlinked title"}]}
        result = JevJudge("test-key", transport=transport).evaluate(case)
        self.assertEqual(result["rubric_version"], "rubric-v4-jev-article")
        self.assertEqual(result["article_count"], 1)
        self.assertEqual(result["events"][0]["supply_impact"], 1)
        self.assertIsNone(result["events"][0]["evidence"])


if __name__ == "__main__":
    unittest.main()
