import io
import json
import unittest

from hardware_signal.cases import build_cases
from hardware_signal.config import Settings
from hardware_signal.openrouter import API_URL, OpenRouterJudge
from dataset import requires_dataset


class FakeResponse(io.BytesIO):
    pass


@requires_dataset
class OpenRouterJudgeTest(unittest.TestCase):
    def test_request_and_validated_response(self):
        case = build_cases(Settings.from_env())[0]
        captured = {}

        def transport(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["auth"] = request.get_header("Authorization")
            captured["body"] = json.loads(request.data)
            answer = {"direction": "FLAT", "confidence": 0.4,
                      "rationale": "Evidence is mixed.", "evidence_ids": []}
            response = {"id": "response-1", "model": "test/model",
                        "choices": [{"message": {"content": json.dumps(answer)}}]}
            return FakeResponse(json.dumps(response).encode())

        result = OpenRouterJudge("secret-test-key", "test/model", transport).evaluate(case)
        self.assertEqual(captured["url"], API_URL)
        self.assertEqual(captured["auth"], "Bearer secret-test-key")
        self.assertEqual(captured["body"]["model"], "test/model")
        self.assertEqual(captured["body"]["messages"][1]["content"], case["user_prompt"])
        self.assertEqual(result["direction"], "FLAT")
        self.assertEqual(result["response_id"], "response-1")


if __name__ == "__main__":
    unittest.main()
