"""OpenRouter Chat Completions adapter with no third-party dependencies."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .judge import Judge, validate_judgment
from .rubric import (SYSTEM_PROMPT as RUBRIC_PROMPT, ARTICLE_SYSTEM_PROMPT,
                     aggregate, validate_rubric)


API_URL = "https://openrouter.ai/api/v1/chat/completions"
HYBRID_PROMPT = """You judge next-month DDR5 retail index direction using TWO independent
inputs: a previously scored news-event rubric and as-of-month price context.
Do not rescore the events. Weigh the news pressure against recent returns,
distance from the trailing six-month mean, and drawdown. A high index or a
positive z-score alone does NOT prove reversal: a shortage can sustain momentum.
Conversely, a positive news score can already be reflected in current prices.
Use only supplied information. Return JSON only with direction (UP, DOWN, FLAT),
confidence (0..1), rationale (one sentence), evidence_ids (supplied article IDs
supporting your judgment), and price_regime (momentum, stretched, neutral,
insufficient_history). FLAT means abstain, not exactly unchanged price.
"""


class OpenRouterJudge(Judge):
    def __init__(self, api_key, model, transport=None):
        if not api_key or not model:
            raise ValueError("Set OPENROUTER_API_KEY and OPENROUTER_MODEL in .env")
        self.api_key = api_key
        self.model = model
        self.transport = transport or urlopen

    def complete(self, system_prompt, user_prompt):
        payload = {"model": self.model, "temperature": 0,
                   "messages": [
                       {"role": "system", "content": system_prompt},
                       {"role": "user", "content": user_prompt},
                   ]}
        request = Request(API_URL, data=json.dumps(payload).encode(), method="POST",
                          headers={"Authorization": f"Bearer {self.api_key}",
                                   "Content-Type": "application/json"})
        try:
            with self.transport(request, timeout=60) as response:
                result = json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f"OpenRouter returned HTTP {exc.code}") from None
        except URLError as exc:
            raise RuntimeError(f"OpenRouter request failed: {exc.reason}") from None
        return result

    def evaluate(self, case):
        result = self.complete(case["system_prompt"], case["user_prompt"])
        try:
            content = result["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ValueError("non-text model response")
            value = json.loads(content)
            value["case_id"] = case["case_id"]
            value["model"] = result.get("model", self.model)
            if isinstance(result.get("id"), str):
                value["response_id"] = result["id"]
            return validate_judgment(case, value)
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid OpenRouter judge response for {case['case_id']}: {exc}") from None

    def evaluate_rubric(self, case):
        user_prompt = json.dumps({"as_of_month": case["as_of_month"],
                                  "target_month": case["target_month"],
                                  "news": case["news"]}, ensure_ascii=False)
        result = self.complete(RUBRIC_PROMPT, user_prompt)
        try:
            content = result["choices"][0]["message"]["content"]
            events = validate_rubric(case, json.loads(content))
            assessment = aggregate(case, events)
            assessment["model"] = result.get("model", self.model)
            if isinstance(result.get("id"), str):
                assessment["response_id"] = result["id"]
            return assessment
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid OpenRouter rubric response for {case['case_id']}: {exc}") from None

    def evaluate_article_rubric(self, case):
        article_news = [article for article in case["news"] if article.get("article_text")]
        if not article_news:
            raise ValueError("case has no cached article text")
        case = {**case, "news": article_news}
        user_prompt = json.dumps({"as_of_month": case["as_of_month"],
                                  "target_month": case["target_month"],
                                  "news": case["news"]}, ensure_ascii=False)
        result = self.complete(ARTICLE_SYSTEM_PROMPT, user_prompt)
        try:
            content = result["choices"][0]["message"]["content"]
            events = validate_rubric(case, json.loads(content))
            assessment = aggregate(case, events)
            assessment["rubric_version"] = "rubric-v3-article"
            assessment["article_count"] = sum(bool(a.get("article_text")) for a in case["news"])
            assessment["model"] = result.get("model", self.model)
            if isinstance(result.get("id"), str):
                assessment["response_id"] = result["id"]
            return assessment
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid OpenRouter article rubric response for {case['case_id']}: {exc}") from None

    def evaluate_hybrid(self, case, rubric):
        if rubric.get("case_id") != case["case_id"]:
            raise ValueError("rubric and case ID do not match")
        context = {"as_of_month": case["as_of_month"], "target_month": case["target_month"],
                   "price_context": case["price_context"],
                   "news_rubric": {"direction": rubric["direction"], "score": rubric["score"],
                                   "events": rubric["events"],
                                   "contributions": rubric["contributions"]},
                   "news": case["news"]}
        result = self.complete(HYBRID_PROMPT, json.dumps(context, ensure_ascii=False))
        try:
            content = result["choices"][0]["message"]["content"]
            value = json.loads(content)
            value["case_id"] = case["case_id"]
            value["model"] = result.get("model", self.model)
            if isinstance(result.get("id"), str):
                value["response_id"] = result["id"]
            if value.get("price_regime") not in {"momentum", "stretched", "neutral", "insufficient_history"}:
                raise ValueError("invalid price_regime")
            validated = validate_judgment(case, value)
            validated.update({"price_regime": value["price_regime"],
                              "price_context": case["price_context"],
                              "rubric_version": rubric["rubric_version"],
                              "rubric_score": rubric["score"]})
            return validated
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid OpenRouter hybrid response for {case['case_id']}: {exc}") from None
