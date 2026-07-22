"""
Input validation guardrails for the Financial Approval System.
"""

from backend.config import BUDGET_CEILING, VALID_DEPARTMENTS

BLOCKED_PATTERNS = [
    "drop table", "delete from", "insert into", "update set",
    "union select", "' or '1'='1", "'; --", "<script>",
    "javascript:", "onclick=", "onerror=", "eval(",
    "__import__", "os.system", "subprocess",
]

MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 2000
MAX_JUSTIFICATION_LENGTH = 2000


def validate_request(
    amount: float,
    department: str,
    title: str,
    description: str,
    justification: str,
) -> tuple[bool, str]:
    """Validate a financial request against amount, department, length, and injection rules."""
    amount_ok, amount_message = validate_amount(amount)
    if not amount_ok:
        return False, amount_message

    if department not in VALID_DEPARTMENTS:
        return False, f"Invalid department: {department}"

    if len(title or "") > MAX_TITLE_LENGTH:
        return False, "Title too long"
    if len(description or "") > MAX_DESCRIPTION_LENGTH:
        return False, "Description too long"
    if len(justification or "") > MAX_JUSTIFICATION_LENGTH:
        return False, "Justification too long"

    for field_name, value in [
        ("title", title),
        ("description", description),
        ("justification", justification),
    ]:
        safe, message = sanitize_text(value or "", field_name)
        if not safe:
            return False, message

    return True, "Request validated successfully"


def validate_amount(amount: float) -> tuple[bool, str]:
    """Validate the requested amount."""
    try:
        numeric_amount = float(amount)
    except (TypeError, ValueError):
        return False, "Amount must be a number"

    if numeric_amount <= 0:
        return False, "Amount must be positive"

    if numeric_amount > BUDGET_CEILING:
        return False, f"Amount exceeds budget ceiling of ${BUDGET_CEILING:,.2f}"

    return True, "Amount is valid"


def sanitize_text(text: str, field_name: str = "text") -> tuple[bool, str]:
    """Check text fields for simple injection and script patterns."""
    original_text = "" if text is None else str(text)
    lowered = original_text.lower()

    for pattern in BLOCKED_PATTERNS:
        if pattern in lowered:
            return False, f"Blocked content detected in {field_name}: suspicious pattern"

    return True, original_text
