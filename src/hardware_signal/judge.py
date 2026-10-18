"""Judge output validation and provider contract."""


def validate_judgment(case, value):
    if not isinstance(value, dict):
        raise ValueError("Judgment must be a JSON object")
    if value.get("case_id") != case["case_id"]:
        raise ValueError("case_id does not match")
    if value.get("direction") not in {"UP", "DOWN", "FLAT"}:
        raise ValueError("direction must be UP, DOWN, or FLAT")
    confidence = value.get("confidence")
    if type(confidence) not in (int, float) or not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    if not isinstance(value.get("rationale"), str) or not value["rationale"].strip():
        raise ValueError("rationale is required")
    ids = value.get("evidence_ids")
    valid_ids = {article["id"] for article in case["news"]}
    if not isinstance(ids, list) or any(not isinstance(item, str) or item not in valid_ids for item in ids):
        raise ValueError("evidence_ids must refer to supplied news")
    result = {key: value[key] for key in ("case_id", "direction", "confidence", "rationale", "evidence_ids")}
    for key in ("model", "response_id"):
        if key in value and isinstance(value[key], str):
            result[key] = value[key]
    return result


class Judge:
    def evaluate(self, case):
        """Return a judgment dict. Implement with the chosen model provider."""
        raise NotImplementedError("Configure a concrete judge provider")
