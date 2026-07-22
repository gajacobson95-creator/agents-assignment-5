"""
LangGraph StateGraph assembly for the Financial Approval workflow.
"""

from langgraph.graph import StateGraph, START, END

from backend.agent.state import ApprovalState
from backend.agent.nodes import (
    submit_request,
    assess_risk,
    manager_review,
    validate_budget,
    finance_review,
    final_signoff,
    process_request,
    handle_rejection,
    route_after_submission,
    route_after_risk,
    route_after_manager,
    route_after_budget,
    route_after_finance,
    route_after_final,
)


def create_approval_graph(checkpointer=None):
    """Build and return the compiled Financial Approval StateGraph."""
    graph = StateGraph(ApprovalState)

    graph.add_node("submit_request", submit_request)
    graph.add_node("assess_risk", assess_risk)
    graph.add_node("manager_review", manager_review)
    graph.add_node("validate_budget", validate_budget)
    graph.add_node("finance_review", finance_review)
    graph.add_node("final_signoff", final_signoff)
    graph.add_node("process_request", process_request)
    graph.add_node("handle_rejection", handle_rejection)

    graph.add_edge(START, "submit_request")

    graph.add_conditional_edges(
        "submit_request",
        route_after_submission,
        {
            "assess_risk": "assess_risk",
            "handle_rejection": "handle_rejection",
        },
    )

    graph.add_conditional_edges(
        "assess_risk",
        route_after_risk,
        {
            "validate_budget": "validate_budget",
            "manager_review": "manager_review",
        },
    )

    graph.add_conditional_edges(
        "manager_review",
        route_after_manager,
        {
            "process_request": "process_request",
            "validate_budget": "validate_budget",
            "finance_review": "finance_review",
            "handle_rejection": "handle_rejection",
        },
    )

    graph.add_conditional_edges(
        "validate_budget",
        route_after_budget,
        {
            "process_request": "process_request",
            "manager_review": "manager_review",
            "finance_review": "finance_review",
        },
    )

    graph.add_conditional_edges(
        "finance_review",
        route_after_finance,
        {
            "process_request": "process_request",
            "final_signoff": "final_signoff",
            "handle_rejection": "handle_rejection",
        },
    )

    graph.add_conditional_edges(
        "final_signoff",
        route_after_final,
        {
            "process_request": "process_request",
            "handle_rejection": "handle_rejection",
        },
    )

    graph.add_edge("process_request", END)
    graph.add_edge("handle_rejection", END)

    return graph.compile(checkpointer=checkpointer)
