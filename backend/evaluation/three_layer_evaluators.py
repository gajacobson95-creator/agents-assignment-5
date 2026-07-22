"""
Three-Layer Evaluation Framework for the Financial Approval System.
"""

RISK_LEVELS = ["low", "medium", "high", "critical"]

EXPECTED_REVIEWS_BY_RISK = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}

BUDGET_CEILING = 100_000


def _result(score: float, reasoning: str) -> dict:
    return {"score": float(score), "reasoning": reasoning}


def _list(value):
    return value if isinstance(value, list) else []


def create_approval_path_evaluator():
    """Check whether the observed workflow path matches the expected path."""
    def evaluator(inputs=None, outputs=None, reference_outputs=None, **kwargs):
        outputs = outputs or {}
        reference_outputs = reference_outputs or {}
        actual = _list(outputs.get("approval_path"))
        expected = _list(reference_outputs.get("approval_path"))

        if actual == expected:
            return _result(1.0, "Approval path matches exactly")
        if len(actual) == len(expected):
            return _result(0.5, "Approval path has the expected length but differs in content or order")
        return _result(0.0, "Approval path length does not match expected")

    return evaluator


def create_false_positive_evaluator():
    """Detect approvals that should have been rejected."""
    def evaluator(inputs=None, outputs=None, reference_outputs=None, **kwargs):
        outputs = outputs or {}
        reference_outputs = reference_outputs or {}
        actual = str(outputs.get("status", "")).lower()
        expected = str(reference_outputs.get("status", "")).lower()

        if expected == "rejected" and actual == "approved":
            return _result(0.0, "False positive: request approved when expected rejection")
        return _result(1.0, "No false positive detected")

    return evaluator


def create_false_negative_evaluator():
    """Detect rejections that should have been approved."""
    def evaluator(inputs=None, outputs=None, reference_outputs=None, **kwargs):
        outputs = outputs or {}
        reference_outputs = reference_outputs or {}
        actual = str(outputs.get("status", "")).lower()
        expected = str(reference_outputs.get("status", "")).lower()

        if expected == "approved" and actual == "rejected":
            return _result(0.0, "False negative: request rejected when expected approval")
        return _result(1.0, "No false negative detected")

    return evaluator


def create_human_review_efficiency_evaluator():
    """Compare actual human-review count with the expected count."""
    def evaluator(inputs=None, outputs=None, reference_outputs=None, **kwargs):
        outputs = outputs or {}
        reference_outputs = reference_outputs or {}
        actual = int(outputs.get("human_reviews", 0))
        expected = int(reference_outputs.get("human_reviews", 0))
        delta = abs(actual - expected)

        if delta == 0:
            return _result(1.0, "Human review count matches expected")
        if delta == 1:
            return _result(0.5, "Human review count is off by one")
        return _result(0.0, "Human review count differs by more than one")

    return evaluator


def create_tool_call_accuracy_evaluator():
    """Approximate RAGAS ToolCallAccuracy with deterministic workflow-stage comparison."""
    def evaluator(inputs=None, outputs=None, reference_outputs=None, **kwargs):
        outputs = outputs or {}
        reference_outputs = reference_outputs or {}
        actual = _list(outputs.get("approval_path"))
        expected = _list(reference_outputs.get("approval_path"))

        if actual == expected:
            return _result(1.0, "Tool/workflow call path matches expected exactly")
        if not actual or not expected:
            return _result(0.0, "Missing actual or expected tool path")

        common = sum(1 for stage in actual if stage in expected)
        score = common / max(len(expected), 1)
        return _result(score, f"{common} of {len(expected)} expected workflow stages appeared")

    return evaluator


def create_agent_goal_accuracy_evaluator():
    """Approximate RAGAS AgentGoalAccuracyWithReference by checking final status and reasoning."""
    def evaluator(inputs=None, outputs=None, reference_outputs=None, **kwargs):
        outputs = outputs or {}
        reference_outputs = reference_outputs or {}
        actual_status = str(outputs.get("status", "")).lower()
        expected_status = str(reference_outputs.get("status", "")).lower()
        reasoning = str(outputs.get("reasoning", outputs.get("risk_reasoning", ""))).strip()

        score = 0.0
        reasons = []
        if actual_status == expected_status and actual_status:
            score += 0.7
            reasons.append("status matches")
        else:
            reasons.append("status mismatch")

        if reasoning:
            score += 0.3
            reasons.append("reasoning present")
        else:
            reasons.append("reasoning missing")

        return _result(score, "; ".join(reasons))

    return evaluator


def create_topic_adherence_evaluator():
    """Check that responses stay in the financial approval workflow domain."""
    topic_terms = {
        "financial", "approval", "budget", "request", "risk", "department",
        "manager", "finance", "review", "approved", "rejected", "amount",
    }

    def evaluator(inputs=None, outputs=None, reference_outputs=None, **kwargs):
        outputs = outputs or {}
        text = " ".join(str(v) for v in outputs.values()).lower()
        hits = sum(1 for term in topic_terms if term in text)

        if hits >= 3:
            return _result(1.0, "Output stays on the financial approval topic")
        if hits >= 1:
            return _result(0.5, "Output is partially related to financial approvals")
        return _result(0.0, "Output appears off-topic")

    return evaluator


def create_policy_adherence_evaluator():
    """Check core policy constraints for approval decisions."""
    def evaluator(inputs=None, outputs=None, reference_outputs=None, **kwargs):
        inputs = inputs or {}
        outputs = outputs or {}

        checks = []
        amount = float(inputs.get("amount", 0) or 0)
        status = str(outputs.get("status", "")).lower()
        risk_level = str(outputs.get("risk_level", inputs.get("risk_level", ""))).lower()
        human_reviews = int(outputs.get("human_reviews", 0) or 0)

        over_ceiling_ok = not (amount > BUDGET_CEILING and status == "approved")
        checks.append((over_ceiling_ok, "over-ceiling requests must be rejected"))

        negative_ok = not (amount <= 0 and status == "approved")
        checks.append((negative_ok, "negative or zero amount requests must be rejected"))

        required_reviews = EXPECTED_REVIEWS_BY_RISK.get(risk_level, 0)
        review_ok = status != "approved" or human_reviews >= required_reviews
        checks.append((review_ok, f"approved {risk_level} risk requests require {required_reviews} human reviews"))

        passed = sum(1 for ok, _ in checks if ok)
        failed = [msg for ok, msg in checks if not ok]
        score = passed / len(checks)
        reasoning = "All policy rules satisfied" if not failed else "; ".join(failed)
        return _result(score, reasoning)

    return evaluator


def create_hallucination_evaluator():
    """Heuristically detect unsupported fabricated details in workflow output."""
    suspicious_terms = ["policy #", "policy number", "cfo said", "board approved", "wire transfer completed"]

    def evaluator(inputs=None, outputs=None, reference_outputs=None, **kwargs):
        outputs = outputs or {}
        text = " ".join(str(v) for v in outputs.values()).lower()
        found = [term for term in suspicious_terms if term in text]

        if found:
            return _result(0.0, f"Potential fabricated details detected: {', '.join(found)}")
        return _result(1.0, "No hallucination patterns detected")

    return evaluator


def create_audit_trail_evaluator():
    """Validate that decision/audit entries are present and structured."""
    required_keys = {"stage", "decision", "reasoning"}

    def evaluator(inputs=None, outputs=None, reference_outputs=None, **kwargs):
        outputs = outputs or {}
        reference_outputs = reference_outputs or {}
        decisions = outputs.get("decisions", [])
        if not isinstance(decisions, list):
            decisions = []

        checks = []

        checks.append((len(decisions) > 0, "decisions list is non-empty"))

        keys_ok = bool(decisions) and all(
            required_keys.issubset(set(decision.keys()))
            for decision in decisions
            if isinstance(decision, dict)
        )
        checks.append((keys_ok, "each decision has stage, decision, and reasoning"))

        if isinstance(reference_outputs.get("decisions"), list):
            expected_count = len(reference_outputs["decisions"])
            count_ok = len(decisions) == expected_count
        elif "expected_decision_count" in reference_outputs:
            count_ok = len(decisions) == int(reference_outputs["expected_decision_count"])
        else:
            count_ok = len(decisions) > 0
        checks.append((count_ok, "decision count matches expected"))

        passed = sum(1 for ok, _ in checks if ok)
        failed = [msg for ok, msg in checks if not ok]
        score = passed / len(checks)
        reasoning = "Audit trail complete" if not failed else "; ".join(failed)
        return _result(score, reasoning)

    return evaluator
