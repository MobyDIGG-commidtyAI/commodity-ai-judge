"""TypeSafe Jev article rubric through OpenRouter's Decisions API."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .rubric import CATEGORIES, aggregate


API_URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.14"


def _choice(instructions, criteria):
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


QUESTIONS = {
    "supply_impact": _choice(
        "What is the article-supported effect on available DDR5 supply? Positive means less supply. Do not infer a DDR5 effect from HBM alone without an explicit shared-capacity link.",
        {"minus_2": "Strong increase in DDR5 supply", "minus_1": "Modest increase in DDR5 supply",
         "zero": "No supported DDR5 supply change", "plus_1": "Modest reduction in DDR5 supply",
         "plus_2": "Strong reduction in DDR5 supply"}),
    "demand_impact": _choice(
        "What is the article-supported effect on DDR5 buying demand? Positive means more demand.",
        {"minus_2": "Strong DDR5 demand decline", "minus_1": "Modest DDR5 demand decline",
         "zero": "No supported DDR5 demand change", "plus_1": "Modest DDR5 demand growth",
         "plus_2": "Strong DDR5 demand growth"}),
    "production_disruption": _choice(
        "What unplanned physical DRAM production interruption is reported? Planned cuts do not count.",
        {"0": "None", "1": "Brief localized issue", "2": "Material plant interruption",
         "3": "Major multi-day outage", "4": "Severe multi-site or prolonged loss"}),
    "market_scope": _choice(
        "What is the scope of the supported DDR5 effect, rather than the general article topic?",
        {"0": "No supported DDR5 effect", "1": "One company", "2": "One product segment",
         "3": "DRAM industry", "4": "Global semiconductor supply chain"}),
    "duration_horizon": _choice(
        "How long is the article-supported DDR5 effect expected to persist?",
        {"0": "Less than one week", "1": "One week to less than a month",
         "2": "One to three months", "3": "Over three to twelve months",
         "4": "Over one year"}),
    "event_category": _choice(
        "Which single event category best describes the article? Choose other if none fits.",
        {category: category.replace("_", " ") for category in sorted(CATEGORIES)}),
    "event_certainty": {"type": "noul", "instructions":
        "Is the described event confirmed to have occurred, or firmly scheduled by a credible source? A rumor or speculation is false."},
    "impact_confidence": {"type": "noul", "instructions":
        "Does this article provide direct, specific evidence of the claimed DDR5 supply or demand effect? Indirect HBM or generic memory effects without an explicit DDR5 link are false."},
}
IMPACT_CHOICES = {"minus_2": -2, "minus_1": -1, "zero": 0, "plus_1": 1, "plus_2": 2}


class JevJudge:
    questions = QUESTIONS
    target = "next-month DDR5 retail price pressure"
    rubric_version = "rubric-v4-jev-article"

    def __init__(self, api_key, model=MODEL, transport=None):
        if not api_key:
            raise ValueError("Set OPENROUTER_API_KEY in .env")
        self.api_key = api_key
        self.model = model
        self.transport = transport or urlopen

    def _decide(self, article, case):
        payload = {"model": self.model,
                   "state": {"as_of_month": case["as_of_month"],
                             "target": self.target,
                             "title": article["title"], "article_text": article["article_text"]},
                   "questions": self.questions}
        request = Request(API_URL, data=json.dumps(payload).encode(), method="POST",
                          headers={"Authorization": f"Bearer {self.api_key}",
                                   "Content-Type": "application/json"})
        try:
            with self.transport(request, timeout=60) as response:
                return json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f"OpenRouter Decisions API returned HTTP {exc.code}") from None
        except URLError as exc:
            raise RuntimeError(f"OpenRouter Decisions API failed: {exc.reason}") from None

    def evaluate(self, case):
        articles = [a for a in case["news"] if a.get("article_text")]
        if not articles:
            raise ValueError("case has no cached article text")
        events, decisions = [], []
        for article in articles:
            result = self._decide(article, case)
            answers = result.get("answers", {})
            if set(answers) != set(self.questions):
                raise ValueError("Jev response has missing or extra rubric answers")

            def chosen(key, mapping=None):
                answer = answers[key]
                value = answer.get("choice")
                if answer.get("type") != "choice" or value not in self.questions[key]["criteria"]:
                    raise ValueError(f"invalid Jev {key} choice")
                return mapping[value] if mapping else value

            def probability(key):
                answer = answers[key]
                value = answer.get("noul")
                if answer.get("type") != "noul" or type(value) not in (int, float) or not 0 <= value <= 1:
                    raise ValueError(f"invalid Jev {key} probability")
                return value

            supply = chosen("supply_impact", IMPACT_CHOICES)
            demand = chosen("demand_impact", IMPACT_CHOICES)
            disruption = int(chosen("production_disruption"))
            scope = int(chosen("market_scope"))
            confidence = probability("impact_confidence") if any((supply, demand, disruption)) else 0.0
            if any((supply, demand, disruption)) and scope == 0:
                supply = demand = disruption = 0
                confidence = 0.0
            events.append({"article_id": article["id"], "supply_impact": supply,
                           "demand_impact": demand, "production_disruption": disruption,
                           "market_scope": scope, "duration_horizon": int(chosen("duration_horizon")),
                           "event_category": chosen("event_category"),
                           "event_certainty": probability("event_certainty"),
                           "impact_confidence": confidence,
                           "evidence": None})
            decisions.append({"article_id": article["id"], "response_id": result.get("id"),
                              "model": result.get("model", self.model), "answers": answers,
                              "usage": result.get("usage")})
        assessment = aggregate(case, events)
        assessment.update({"rubric_version": self.rubric_version,
                           "article_count": len(articles), "model": self.model,
                           "jev_decisions": decisions})
        return assessment
