"""
Custom LangSmith evaluators for the Financial Approval System.
"""

RISK_LEVELS = ["low", "medium", "high", "critical"]


def _score_result(score: float, reasoning: str) -> dict:
    return {"score": float(score), "reasoning": reasoning}


def create_risk_accuracy_evaluator():
    """Create an evaluator that scores exact, adjacent, and non-adjacent risk predictions."""
    def evaluator(inputs=None, outputs=None, reference_outputs=None, **kwargs):
        outputs = outputs or {}
        reference_outputs = reference_outputs or kwargs.get("reference_outputs") or {}

        predicted = str(outputs.get("risk_level", "")).lower()
        expected = str(reference_outputs.get("risk_level", "")).lower()

        if predicted == expected and predicted in RISK_LEVELS:
            return _score_result(1.0, "Risk level matches exactly")

        if predicted in RISK_LEVELS and expected in RISK_LEVELS:
            if abs(RISK_LEVELS.index(predicted) - RISK_LEVELS.index(expected)) == 1:
                return _score_result(0.5, "Risk level is adjacent to expected")

        return _score_result(0.0, f"Risk mismatch: predicted={predicted}, expected={expected}")

    return evaluator


def create_approval_consistency_evaluator():
    """Create an evaluator that checks final approval status consistency."""
    def evaluator(inputs=None, outputs=None, reference_outputs=None, **kwargs):
        outputs = outputs or {}
        reference_outputs = reference_outputs or kwargs.get("reference_outputs") or {}

        predicted = str(outputs.get("status", "")).lower()
        expected = str(reference_outputs.get("status", "")).lower()

        if predicted == expected and predicted:
            return _score_result(1.0, "Approval status matches expected")

        return _score_result(0.0, f"Approval status mismatch: predicted={predicted}, expected={expected}")

    return evaluator
