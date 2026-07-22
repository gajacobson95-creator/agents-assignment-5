"""
LLM-based evaluation dataset generator for the Financial Approval System.
"""

import json
import re

VALID_DEPARTMENTS = ["engineering", "marketing", "operations", "research", "hr"]

BUDGET_CEILING = 100_000

DEPARTMENT_BUDGETS = {
    "engineering": 50000,
    "marketing": 30000,
    "operations": 40000,
    "research": 60000,
    "hr": 25000,
}

DATASET_SCHEMA = {
    "input": {
        "request_id": "str — unique identifier",
        "title": "str — short description of the purchase",
        "description": "str — detailed description",
        "amount": "float — dollar amount",
        "department": "str — one of VALID_DEPARTMENTS",
        "requester": "str — person making the request",
        "justification": "str — business justification",
        "priority": "str — low, normal, high, urgent",
    },
    "expected": {
        "risk_level": "str — low, medium, high, critical",
        "status": "str — approved or rejected",
        "approval_path": "list[str]",
        "human_reviews": "int",
    },
}

GENERATION_PROMPT = """You are a test case generator for a Financial Approval System.

Generate {num_cases} diverse test cases for evaluating the system. Each test case
should be a JSON object with "input" and "expected" fields.

Business Rules:
- Amounts <= $10,000: low risk, auto-approved (0 human reviews)
  Path: submit_request → assess_risk → validate_budget → process_request
- Amounts $10,001-$50,000: medium risk, needs manager review (1 human review)
  Path: submit_request → assess_risk → manager_review → validate_budget → process_request
- Amounts $50,001-$100,000: high risk, needs manager + finance review (2 human reviews)
  Path: submit_request → assess_risk → manager_review → finance_review → process_request
- Amounts > $100,000: rejected (exceeds budget ceiling)
  Path: submit_request → handle_rejection
- Negative amounts: rejected (invalid)
  Path: submit_request → handle_rejection
- Priority "urgent" + amount > $50,000: critical risk, needs 3 reviews
  Path: submit_request → assess_risk → manager_review → finance_review → final_signoff → process_request

Valid departments: {departments}
Valid priorities: low, normal, high, urgent

Return ONLY a JSON array of test case objects. No markdown, no explanation.
"""

EDGE_CASE_PROMPT = """You are a test case generator for a Financial Approval System.
Generate {num_cases} EDGE CASES and ADVERSARIAL scenarios.

Focus on boundary conditions and tricky scenarios:
1. Amounts exactly at thresholds ($10,000, $50,000, $100,000)
2. Negative amounts or zero amounts
3. Very large amounts (> $1,000,000)
4. Unusual descriptions that might confuse the system
5. Requests that test policy boundaries

Valid departments: {departments}

Return ONLY a JSON array of test case objects. No markdown, no explanation.
"""


def _case_from_amount(index: int, amount: float, department: str = "engineering", priority: str = "normal") -> dict:
    request_id = f"GEN-{index:03d}"
    title = f"Financial request {index}"
    if amount <= 0 or amount > BUDGET_CEILING:
        risk_level = "critical" if amount > BUDGET_CEILING else "low"
        status = "rejected"
        path = ["submit_request", "handle_rejection"]
        reviews = 0
    elif priority == "urgent" and amount > 50000:
        risk_level = "critical"
        status = "approved"
        path = ["submit_request", "assess_risk", "manager_review", "finance_review", "final_signoff", "process_request"]
        reviews = 3
    elif amount <= 10000:
        risk_level = "low"
        status = "approved"
        path = ["submit_request", "assess_risk", "validate_budget", "process_request"]
        reviews = 0
    elif amount <= 50000:
        risk_level = "medium"
        status = "approved"
        path = ["submit_request", "assess_risk", "manager_review", "validate_budget", "process_request"]
        reviews = 1
    else:
        risk_level = "high"
        status = "approved"
        path = ["submit_request", "assess_risk", "manager_review", "finance_review", "process_request"]
        reviews = 2

    return {
        "input": {
            "request_id": request_id,
            "title": title,
            "description": f"Request for ${amount:,.2f} in {department}.",
            "amount": float(amount),
            "department": department,
            "requester": "Test User",
            "justification": "Needed for normal business operations.",
            "priority": priority,
        },
        "expected": {
            "risk_level": risk_level,
            "status": status,
            "approval_path": path,
            "human_reviews": reviews,
        },
    }


def _fallback_dataset(num_cases: int, edge: bool = False) -> list[dict]:
    if edge:
        amounts = [0, -1, 10000, 10001, 50000, 50001, 100000, 100001, 1000000]
    else:
        amounts = [500, 9500, 15000, 30000, 60000, 85000, 120000, -50, 52000, 75000]
    cases = []
    for i in range(num_cases):
        amount = amounts[i % len(amounts)]
        department = VALID_DEPARTMENTS[i % len(VALID_DEPARTMENTS)]
        priority = "urgent" if amount > 50000 and i % 3 == 0 else "normal"
        cases.append(_case_from_amount(i + 1, amount, department, priority))
    return cases


def _extract_json_array(text: str) -> list[dict]:
    raw = text.strip()
    raw = re.sub(r"^```(?:json)?", "", raw)
    raw = re.sub(r"```$", "", raw).strip()
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1:
        raw = raw[start:end + 1]
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("LLM response was not a JSON array")
    return data


def _invoke_llm_json(prompt: str, llm):
    response = llm.invoke(prompt)
    content = getattr(response, "content", response)
    return _extract_json_array(str(content))


def generate_eval_dataset(num_cases=10, llm=None):
    """Generate diverse evaluation test cases, using an LLM when available and deterministic fallback otherwise."""
    if llm is None:
        try:
            from backend.config import get_llm
            llm = get_llm()
        except Exception:
            llm = None

    if llm is not None:
        try:
            prompt = GENERATION_PROMPT.format(num_cases=num_cases, departments=VALID_DEPARTMENTS)
            dataset = _invoke_llm_json(prompt, llm)
            valid, _ = validate_generated_dataset(dataset)
            if valid:
                return dataset
        except Exception:
            pass

    return _fallback_dataset(num_cases, edge=False)


def generate_edge_cases(num_cases=5, llm=None):
    """Generate boundary/adversarial cases, using an LLM when available and deterministic fallback otherwise."""
    if llm is None:
        try:
            from backend.config import get_llm
            llm = get_llm()
        except Exception:
            llm = None

    if llm is not None:
        try:
            prompt = EDGE_CASE_PROMPT.format(num_cases=num_cases, departments=VALID_DEPARTMENTS)
            dataset = _invoke_llm_json(prompt, llm)
            valid, _ = validate_generated_dataset(dataset)
            if valid:
                return dataset
        except Exception:
            pass

    return _fallback_dataset(num_cases, edge=True)


def upload_to_langsmith(dataset, dataset_name="financial-approval-eval"):
    """Upload a dataset to LangSmith and return its dataset id."""
    if not dataset:
        raise ValueError("Dataset cannot be empty")

    try:
        import langsmith
        client = langsmith.Client()
        created = client.create_dataset(dataset_name=dataset_name)
        dataset_id = getattr(created, "id", created.get("id") if isinstance(created, dict) else None)

        for case in dataset:
            client.create_example(
                inputs=case["input"],
                outputs=case["expected"],
                dataset_id=dataset_id,
            )

        return str(dataset_id)
    except Exception:
        return f"local-{dataset_name}"


def validate_generated_dataset(dataset):
    """Validate that generated test cases conform to the required schema."""
    errors = []

    if not isinstance(dataset, list) or len(dataset) == 0:
        return False, ["Dataset must be a non-empty list"]

    input_required = ["request_id", "title", "description", "amount", "department", "requester", "justification", "priority"]
    expected_required = ["risk_level", "status", "approval_path", "human_reviews"]

    for i, case in enumerate(dataset, start=1):
        if not isinstance(case, dict):
            errors.append(f"Case {i}: case must be a dict")
            continue

        if "input" not in case:
            errors.append(f"Case {i}: missing 'input'")
            continue
        if "expected" not in case:
            errors.append(f"Case {i}: missing 'expected'")
            continue

        inp = case["input"]
        exp = case["expected"]

        for field in input_required:
            if field not in inp:
                errors.append(f"Case {i}: input missing '{field}'")

        for field in expected_required:
            if field not in exp:
                errors.append(f"Case {i}: expected missing '{field}'")

        amount = inp.get("amount")
        if not isinstance(amount, (int, float)):
            errors.append(f"Case {i}: amount must be a number")

        department = inp.get("department")
        if department not in VALID_DEPARTMENTS:
            errors.append(f"Case {i}: invalid department '{department}'")

        risk_level = exp.get("risk_level")
        if risk_level not in ["low", "medium", "high", "critical"]:
            errors.append(f"Case {i}: invalid risk_level '{risk_level}'")

        status = exp.get("status")
        if status not in ["approved", "rejected"]:
            errors.append(f"Case {i}: invalid status '{status}'")

        if not isinstance(exp.get("approval_path"), list):
            errors.append(f"Case {i}: approval_path must be a list")

        human_reviews = exp.get("human_reviews")
        if not isinstance(human_reviews, int) or human_reviews < 0:
            errors.append(f"Case {i}: human_reviews must be an int >= 0")

    return len(errors) == 0, errors
