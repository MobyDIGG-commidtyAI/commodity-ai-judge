import io
import unittest

from hardware_signal.article_cache import fetch_article, with_article_text
from hardware_signal.cases import build_cases
from hardware_signal.config import Settings
from hardware_signal.rubric import validate_rubric
from dataset import requires_article_cache, requires_dataset


class FakeResponse(io.BytesIO):
    url = "https://example.com/story"
    headers = {"Content-Type": "text/html; charset=utf-8"}


@requires_dataset
class ArticleCacheTest(unittest.TestCase):
    def test_fetch_extracts_dated_body(self):
        paragraph = "DDR5 supply declined after a verified factory outage. " * 16
        html = ("<script type='application/ld+json'>"
                '{"@type":"NewsArticle","headline":"DDR5 supply update",'
                '"datePublished":"2025-10-05T10:00:00Z"}</script>'
                f"<article><p>{paragraph}</p></article>")
        article = {"id": "article-test", "date": "2025-10-05", "url": "https://example.com/story"}
        result = fetch_article(article, opener=lambda request, timeout: FakeResponse(html.encode()))
        self.assertEqual(result["status"], "ok")
        self.assertGreater(result["word_count"], 100)
        self.assertEqual(result["source_published_at"][:10], "2025-10-05")

    @requires_article_cache
    def test_cached_article_is_added_to_case(self):
        case = next(c for c in build_cases(Settings.from_env()) if c["case_id"] == "ddr5-2026-08")
        enriched = with_article_text(case)
        self.assertEqual(enriched["news"][0]["content_status"], "article_text")
        self.assertGreater(len(enriched["news"][0]["article_text"].split()), 100)

    def test_undated_page_uses_dataset_date(self):
        from unittest.mock import patch

        case = {"as_of_month": "2026-10", "news": [{"id": "ohm-test", "date": "2026-10-09",
                "title": "GPU prices", "url": "https://example.com/story"}]}
        cache = {"status": "ok", "body": "GPU supply changed. " * 100,
                 "source_url": "https://example.com/story", "source_published_at": None}
        with patch("hardware_signal.article_cache.load_cached_article", return_value=cache):
            article = with_article_text(case)["news"][0]
        self.assertEqual(article["article_published_at"], "2026-10-09")
        self.assertEqual(article["article_date_source"], "dataset")

    def test_extracts_cnbc_style_article_body(self):
        paragraph = "Consumer GPU prices rose because retail graphics card supply fell. " * 12
        html = f'<div class="ArticleBody-articleBody"><p>{paragraph}</p></div>'
        article = {"id": "article-test", "date": "2026-08-22", "url": "https://example.com/story"}
        result = fetch_article(article, opener=lambda request, timeout: FakeResponse(html.encode()))
        self.assertEqual(result["status"], "ok")
        self.assertGreater(result["word_count"], 100)

    def test_dated_report_can_use_main_content(self):
        paragraph = "This dated report summarizes cloud GPU rental prices and available capacity. " * 12
        html = ('<script type="application/ld+json">'
                '{"@type":"WebPage","datePublished":"2026-06-26T00:00:00Z"}'
                '</script><main><p>' + paragraph + '</p></main>')
        article = {"id": "article-test", "date": "2026-06-29", "url": "https://example.com/report"}
        result = fetch_article(article, opener=lambda request, timeout: FakeResponse(html.encode()))
        self.assertEqual(result["status"], "ok")
        self.assertGreater(result["word_count"], 100)

    def test_evidence_can_cite_article_body(self):
        case = {"news": [{"id": "a", "title": "Memory report",
                          "article_text": "Factory outage reduced DDR5 supply."}]}
        event = {"article_id": "a", "supply_impact": 1, "demand_impact": 0,
                 "production_disruption": 2, "market_scope": 2,
                 "duration_horizon": 2, "event_category": "plant_outage",
                 "event_certainty": 1, "impact_confidence": 0.8,
                 "evidence": "Factory outage reduced DDR5 supply"}
        self.assertEqual(validate_rubric(case, {"events": [event]}), [event])


if __name__ == "__main__":
    unittest.main()
