import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hardware_signal import article_cache
from hardware_signal.config import Settings
from hardware_signal.daily import run_daily, write_atomic


FEED = [
    {"ts": "2026-10-03T10:00:00+00:00", "category": "RAM", "genre": "industry_news", "source": "rss",
     "title": "DRAM makers cut DDR5 output", "url": "https://example.com/ram-1"},
    {"ts": "2026-10-05T10:00:00+00:00", "category": "GPU", "genre": "industry_news", "source": "hn",
     "title": "Graphics card prices rise", "url": "https://example.com/gpu-1"},
    {"ts": "2026-09-20T10:00:00+00:00", "category": "RAM", "genre": "general_news", "source": "rss",
     "title": "Old September headline", "url": "https://example.com/ram-old"},
]


class FakeChat:
    def evaluate_rubric(self, case):
        self.case = case
        return {"case_id": case["case_id"], "rubric_version": "rubric-v2", "direction": "UP", "score": 0.75,
                "events": [{"article_id": case["news"][0]["id"]}],
                "contributions": [{"article_id": case["news"][0]["id"], "contribution": 0.75}], "model": "fake/model"}


class FakeJev:
    def __init__(self, fail=False):
        self.fail = fail

    def evaluate(self, case):
        if self.fail:
            raise RuntimeError("OpenRouter Decisions API returned HTTP 500")
        return {"case_id": case["case_id"], "rubric_version": "gpu-rubric-v1-jev-article", "direction": "FLAT",
                "score": 0.0, "events": [{"article_id": a["id"]} for a in case["news"]],
                "contributions": [{"article_id": a["id"], "contribution": 0.0} for a in case["news"]],
                "model": "typesafe/jev-1.14"}


def fake_fetch(article):
    return {"article_id": article["id"], "status": "ok", "source_url": article["url"],
            "source_published_at": article["date"], "body": "Long article body " * 50}


class DailyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        data = self.tmp / "chin"
        (data / "prices").mkdir(parents=True)
        (data / "prices/retail-and-cloud-price-contract.json").write_text(json.dumps(
            {"gpuRetail": [{"month": "2026-08", "index": 100.0}, {"month": "2026-09", "index": 101.0}]}))
        feed = self.tmp / "news_feed.csv"
        with feed.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(FEED[0]))
            writer.writeheader()
            writer.writerows(FEED)
        env = {"DATA_DIR": str(data), "DB_PATH": str(self.tmp / "judgments.sqlite3"), "NEWS_FEED": str(feed),
               "OPENROUTER_API_KEY": "", "OPENROUTER_MODEL": ""}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        self.cache = mock.patch.object(article_cache, "CACHE_DIR", self.tmp / "article_cache")
        self.cache.start()
        self.settings = Settings.from_env()

    def tearDown(self):
        self.cache.stop()
        self.env.stop()

    def test_scores_latest_month_for_both_categories(self):
        chat = FakeChat()
        payload = run_daily(self.settings, chat_judge=chat, jev_judge=FakeJev(), fetch=fake_fetch)
        self.assertEqual(payload["news_month"], "2026-10")
        self.assertEqual([a["title"] for a in chat.case["news"]], ["DRAM makers cut DDR5 output"])
        ram, gpu = payload["items"]["DDR5"], payload["items"]["GPU"]
        self.assertEqual((ram["status"], ram["direction"], ram["pressure"]), ("SCORED", "UP", 0.75))
        self.assertEqual(ram["target_month"], "2026-11")
        self.assertEqual(ram["evidence"][0]["url"], "https://example.com/ram-1")
        self.assertEqual((gpu["status"], gpu["articles_judged"]), ("SCORED", 1))
        self.assertTrue((self.tmp / "article_cache").exists())

    def test_one_failing_category_keeps_the_other(self):
        payload = run_daily(self.settings, chat_judge=FakeChat(), jev_judge=FakeJev(fail=True), fetch=fake_fetch)
        self.assertEqual(payload["items"]["GPU"]["status"], "ERROR")
        self.assertEqual(payload["items"]["DDR5"]["status"], "SCORED")

    def test_month_without_articles_is_not_scored(self):
        payload = run_daily(self.settings, month="2026-07", chat_judge=FakeChat(), jev_judge=FakeJev(), fetch=fake_fetch)
        self.assertEqual(payload["items"]["DDR5"]["status"], "NO_NEWS")
        self.assertEqual(payload["items"]["GPU"]["status"], "NO_TEXT")
        self.assertIsNone(payload["items"]["DDR5"]["pressure"])

    def test_output_is_valid_json_written_atomically(self):
        payload = run_daily(self.settings, chat_judge=FakeChat(), jev_judge=FakeJev(), fetch=fake_fetch)
        path = write_atomic(payload, self.tmp / "out/judge.json")
        self.assertEqual(json.loads(path.read_text())["schema_version"], 1)
        self.assertEqual([p.name for p in path.parent.iterdir()], ["judge.json"])


if __name__ == "__main__":
    unittest.main()
