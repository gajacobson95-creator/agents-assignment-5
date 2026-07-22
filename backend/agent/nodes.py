"""
Node functions for the Financial Approval workflow.
"""

import json
import os
import re

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import interrupt, Command

from backend.agent.state import ApprovalState
from backend.config import (
    get_llm,
    BUDGET_CEILING,
    DEPARTMENT_BUDGETS,
    HIGH_RISK_THRESHOLD,
    MEDIUM_RISK_THRESHOLD,
)
from backend.guardrails.input_validator import validate_request
from backend.guardrails.output_filter import sanitize_output


def _state_get(state, key, default=None):
    return state.get(key, default) if isinstance(state, dict) else getattr(state, key, default)


def _base_decisions(state):
    decisions = _state_get(state, "decisions", [])
    return list(decisions) if isinstance(decisions, list) else []


def _parse_decision(raw, default_approved=True):
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {"approved": default_approved, "comments": raw}
    if not isinstance(raw, dict):
        raw = {"approved": default_approved, "comments": ""}
    return {
        "approved": bool(raw.get("approved", default_approved)),
        "comments": str(raw.get("comments", "")),
    }


def _heuristic_risk(amount, priority="normal"):
    amount = float(amount or 0)
    priority = str(priority or "normal").lower()
    if priority == "urgent" and amount > HIGH_RISK_THRESHOLD:
        return "critical", "Urgent high-dollar request requires executive-level review."
    if amount > HIGH_RISK_THRESHOLD:
        return "high", "Amount exceeds the high-risk threshold and requires manager and finance review."
    if amount > MEDIUM_RISK_THRESHOLD:
        return "medium", "Amount exceeds the medium-risk threshold and requires manager review."
    return "low", "Amount is within the low-risk threshold and can follow the auto-approval path."


def _parse_risk_response(content, fallback_level, fallback_reason):
    text = str(content).strip()
    lowered = text.lower()

    try:
        parsed = json.loads(text)
        level = str(parsed.get("risk_level", fallback_level)).lower()
        reasoning = str(parsed.get("risk_reasoning", parsed.get("reasoning", fallback_reason)))
        if level in {"low", "medium", "high", "critical"}:
            return level, reasoning
    except Exception:
        pass

    for level in ["critical", "high", "medium", "low"]:
        if re.search(rf"\b{level}\b", lowered):
            return level, text

    return fallback_level, fallback_reason


def submit_request(state: ApprovalState) -> dict:
    """Receive and validate the financial request."""
    is_valid, message = validate_request(
        amount=_state_get(state, "amount", 0),
        department=_state_get(state, "department", ""),
        title=_state_get(state, "title", ""),
        description=_state_get(state, "description", ""),
        justification=_state_get(state, "justification", ""),
    )

    if not is_valid:
        decisions = _base_decisions(state)
        decisions.append({
            "stage": "validation",
            "decision": "rejected",
            "reasoning": message,
            "approved": False,
            "reviewer": "System",
            "comments": message,
        })
        return {
            "is_valid": False,
            "validation_message": message,
            "current_stage": "rejection",
            "status": "rejected",
            "decisions": decisions,
            "messages": [AIMessage(content=f"Request rejected during validation: {message}")],
        }

    summary = (
        f"Request submitted: {_state_get(state, 'title', 'Untitled')} for "
        f"${float(_state_get(state, 'amount', 0)):,.2f} from "
        f"{_state_get(state, 'department', 'unknown')}."
    )
    return {
        "is_valid": True,
        "validation_message": message,
        "current_stage": "risk_assessment",
        "status": "pending",
        "decisions": _base_decisions(state),
        "messages": [AIMessage(content=summary)],
    }


def assess_risk(state: ApprovalState) -> dict:
    """Assess risk level using an LLM when configured, with deterministic fallback."""
    amount = float(_state_get(state, "amount", 0) or 0)
    fallback_level, fallback_reason = _heuristic_risk(amount, _state_get(state, "priority", "normal"))

    prompt = f"""
Assess the financial approval risk as exactly one of: low, medium, high, critical.

Return JSON only with keys risk_level and risk_reasoning.

Request:
Title: {_state_get(state, "title", "")}
Description: {_state_get(state, "description", "")}
Amount: ${amount:,.2f}
Department: {_state_get(state, "department", "")}
Priority: {_state_get(state, "priority", "normal")}
Justification: {_state_get(state, "justification", "")}

Policy:
- Amounts <= ${MEDIUM_RISK_THRESHOLD:,.2f}: low
- Amounts > ${MEDIUM_RISK_THRESHOLD:,.2f} and <= ${HIGH_RISK_THRESHOLD:,.2f}: medium
- Amounts > ${HIGH_RISK_THRESHOLD:,.2f}: high
- Urgent priority with amount > ${HIGH_RISK_THRESHOLD:,.2f}: critical
""".strip()

    risk_level, risk_reasoning = fallback_level, fallback_reason
    has_key = bool(os.getenv("OPENAI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    if has_key:
        try:
            response = get_llm().invoke([HumanMessage(content=prompt)])
            risk_level, risk_reasoning = _parse_risk_response(
                getattr(response, "content", response),
                fallback_level,
                fallback_reason,
            )
        except Exception:
            risk_level, risk_reasoning = fallback_level, fallback_reason

    decisions = _base_decisions(state)
    decisions.append({
        "stage": "risk_assessment",
        "decision": risk_level,
        "reasoning": risk_reasoning,
        "approved": True,
        "reviewer": "AI Risk Assessor",
        "comments": risk_reasoning,
    })

    return {
        "risk_level": risk_level,
        "risk_reasoning": risk_reasoning,
        "current_stage": "manager_review" if risk_level != "low" else "budget_validation",
        "decisions": decisions,
        "messages": [AIMessage(content=f"Risk assessed as {risk_level}: {risk_reasoning}")],
    }


def manager_review(state: ApprovalState) -> dict:
    """Pause for manager human-in-the-loop review."""
    decision = interrupt({
        "type": "manager_review",
        "request_id": _state_get(state, "request_id", ""),
        "title": _state_get(state, "title", ""),
        "amount": _state_get(state, "amount", 0),
        "department": _state_get(state, "department", ""),
        "risk_level": _state_get(state, "risk_level", ""),
        "risk_reasoning": _state_get(state, "risk_reasoning", ""),
    })
    parsed = _parse_decision(decision)
    approved = parsed["approved"]
    comments = parsed["comments"]

    decisions = _base_decisions(state)
    decisions.append({
        "stage": "manager_review",
        "decision": "approved" if approved else "rejected",
        "reasoning": comments or "Manager decision recorded",
        "approved": approved,
        "reviewer": "Manager",
        "comments": comments,
    })

    return {
        "manager_approved": approved,
        "manager_comments": comments,
        "current_stage": "budget_validation" if approved else "rejection",
        "status": "pending" if approved else "rejected",
        "decisions": decisions,
        "messages": [AIMessage(content=f"Manager {'approved' if approved else 'rejected'} the request. {comments}")],
    }


def validate_budget(state: ApprovalState) -> dict:
    """Validate the request against the configured department budget."""
    department = _state_get(state, "department", "")
    amount = float(_state_get(state, "amount", 0) or 0)
    budget = float(DEPARTMENT_BUDGETS.get(department, 0))
    remaining = budget - amount
    within_budget = amount <= budget

    decisions = _base_decisions(state)
    decisions.append({
        "stage": "budget_validation",
        "decision": "within_budget" if within_budget else "over_budget",
        "reasoning": f"Department budget is ${budget:,.2f}; remaining after request would be ${remaining:,.2f}.",
        "approved": within_budget,
        "reviewer": "System",
        "comments": "Within department budget" if within_budget else "Request exceeds department budget",
    })

    return {
        "department_budget": budget,
        "budget_remaining": remaining,
        "within_budget": within_budget,
        "current_stage": "processing" if within_budget else "escalation",
        "decisions": decisions,
        "messages": [AIMessage(content=f"Budget validation: {'within budget' if within_budget else 'over budget'} (${remaining:,.2f} remaining).")],
    }


def finance_review(state: ApprovalState) -> dict:
    """Pause for finance-team human-in-the-loop review."""
    decision = interrupt({
        "type": "finance_review",
        "request_id": _state_get(state, "request_id", ""),
        "title": _state_get(state, "title", ""),
        "amount": _state_get(state, "amount", 0),
        "department": _state_get(state, "department", ""),
        "risk_level": _state_get(state, "risk_level", ""),
        "within_budget": _state_get(state, "within_budget", None),
        "department_budget": _state_get(state, "department_budget", 0),
        "budget_remaining": _state_get(state, "budget_remaining", 0),
        "manager_comments": _state_get(state, "manager_comments", ""),
    })
    parsed = _parse_decision(decision)
    approved = parsed["approved"]
    comments = parsed["comments"]

    decisions = _base_decisions(state)
    decisions.append({
        "stage": "finance_review",
        "decision": "approved" if approved else "rejected",
        "reasoning": comments or "Finance decision recorded",
        "approved": approved,
        "reviewer": "Finance",
        "comments": comments,
    })

    return {
        "finance_approved": approved,
        "finance_comments": comments,
        "current_stage": "final_signoff" if approved and _state_get(state, "risk_level", "") == "critical" else ("processing" if approved else "rejection"),
        "status": "pending" if approved else "rejected",
        "decisions": decisions,
        "messages": [AIMessage(content=f"Finance {'approved' if approved else 'rejected'} the request. {comments}")],
    }


def final_signoff(state: ApprovalState) -> dict:
    """Pause for executive final sign-off."""
    decision = interrupt({
        "type": "final_signoff",
        "request_id": _state_get(state, "request_id", ""),
        "title": _state_get(state, "title", ""),
        "amount": _state_get(state, "amount", 0),
        "department": _state_get(state, "department", ""),
        "risk_level": _state_get(state, "risk_level", ""),
        "manager_approved": _state_get(state, "manager_approved", None),
        "finance_approved": _state_get(state, "finance_approved", None),
        "within_budget": _state_get(state, "within_budget", None),
        "decisions": _base_decisions(state),
    })
    parsed = _parse_decision(decision)
    approved = parsed["approved"]
    comments = parsed["comments"]

    decisions = _base_decisions(state)
    decisions.append({
        "stage": "final_signoff",
        "decision": "approved" if approved else "rejected",
        "reasoning": comments or "Executive sign-off decision recorded",
        "approved": approved,
        "reviewer": "Executive",
        "comments": comments,
    })

    return {
        "final_approved": approved,
        "final_comments": comments,
        "current_stage": "processing" if approved else "rejection",
        "status": "pending" if approved else "rejected",
        "decisions": decisions,
        "messages": [AIMessage(content=f"Executive final sign-off {'approved' if approved else 'rejected'} the request. {comments}")],
    }


def process_request(state: ApprovalState) -> dict:
    """Process the fully approved request."""
    decisions = _base_decisions(state)
    path = [decision.get("stage", "") for decision in decisions if decision.get("stage")]
    human_reviews = sum(1 for decision in decisions if decision.get("reviewer") in {"Manager", "Finance", "Executive"})

    summary_lines = [
        f"Request {_state_get(state, 'request_id', '')} approved.",
        f"Title: {_state_get(state, 'title', '')}",
        f"Amount: ${float(_state_get(state, 'amount', 0) or 0):,.2f}",
        f"Department: {_state_get(state, 'department', '')}",
        f"Risk level: {_state_get(state, 'risk_level', 'low')}",
        f"Approval path: {' -> '.join(path + ['process_request'])}",
    ]

    for decision in decisions:
        summary_lines.append(
            f"{decision.get('stage')}: {decision.get('decision')} — {decision.get('comments') or decision.get('reasoning', '')}"
        )

    summary = sanitize_output("\n".join(summary_lines))

    return {
        "status": "approved",
        "current_stage": "complete",
        "approval_path": path + ["process_request"],
        "human_reviews": human_reviews,
        "messages": [AIMessage(content=summary)],
    }


def handle_rejection(state: ApprovalState) -> dict:
    """Handle rejected requests with a sanitized rejection summary."""
    decisions = _base_decisions(state)
    rejection = next(
        (decision for decision in reversed(decisions) if decision.get("approved") is False or decision.get("decision") == "rejected"),
        None,
    )
    stage = rejection.get("stage", "validation") if rejection else "validation"
    reason = rejection.get("comments") or rejection.get("reasoning") if rejection else _state_get(state, "validation_message", "Request rejected")

    path = [decision.get("stage", "") for decision in decisions if decision.get("stage")]
    summary = sanitize_output(
        f"Request {_state_get(state, 'request_id', '')} rejected at {stage}. Reason: {reason}"
    )

    return {
        "status": "rejected",
        "current_stage": "complete",
        "approval_path": path + ["handle_rejection"],
        "human_reviews": sum(1 for decision in decisions if decision.get("reviewer") in {"Manager", "Finance", "Executive"}),
        "messages": [AIMessage(content=summary)],
    }


def route_after_submission(state: ApprovalState) -> str:
    """Route validated requests to risk assessment and invalid requests to rejection."""
    return "assess_risk" if _state_get(state, "is_valid", False) is True else "handle_rejection"


def route_after_risk(state: ApprovalState) -> str:
    """Route low-risk requests to budget validation and all others to manager review."""
    return "validate_budget" if _state_get(state, "risk_level", "medium") == "low" else "manager_review"


def route_after_manager(state: ApprovalState) -> str:
    """Route after manager review based on approval and risk level."""
    if _state_get(state, "manager_approved", False) is not True:
        return "handle_rejection"

    risk_level = _state_get(state, "risk_level", "medium")
    if risk_level == "low":
        return "process_request"
    if risk_level == "medium":
        return "validate_budget"
    return "finance_review"


def route_after_budget(state: ApprovalState) -> str:
    """Route after budget validation."""
    if _state_get(state, "within_budget", False) is True:
        return "process_request"

    risk_level = _state_get(state, "risk_level", "medium")
    if risk_level == "low":
        return "manager_review"
    return "finance_review"


def route_after_finance(state: ApprovalState) -> str:
    """Route after finance review."""
    if _state_get(state, "finance_approved", False) is not True:
        return "handle_rejection"
    return "final_signoff" if _state_get(state, "risk_level", "") == "critical" else "process_request"


def route_after_final(state: ApprovalState) -> str:
    """Route after executive final sign-off."""
    return "process_request" if _state_get(state, "final_approved", False) is True else "handle_rejection"
