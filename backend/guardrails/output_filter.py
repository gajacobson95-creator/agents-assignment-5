"""
Output filtering guardrails for the Financial Approval System.
"""

import re

PII_PATTERNS = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "phone": re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),
}


def sanitize_output(text: str) -> str:
    """Mask SSNs, credit cards, emails, and phone numbers in output text."""
    sanitized = "" if text is None else str(text)
    sanitized = PII_PATTERNS["ssn"].sub("***-**-XXXX", sanitized)
    sanitized = PII_PATTERNS["credit_card"].sub("****-****-****-XXXX", sanitized)
    sanitized = PII_PATTERNS["email"].sub("[EMAIL REDACTED]", sanitized)
    sanitized = PII_PATTERNS["phone"].sub("***-***-XXXX", sanitized)
    return sanitized


def mask_financial_details(text: str) -> str:
    """Mask dollar amounts and long account numbers while preserving useful context."""
    masked = "" if text is None else str(text)

    def mask_amount(match: re.Match) -> str:
        value = match.group(0)
        body = value[1:]
        if "." in body:
            whole, cents = body.rsplit(".", 1)
            cents = "." + cents
        else:
            whole, cents = body, ""
        digits = re.sub(r"\D", "", whole)
        visible = digits[-3:] if len(digits) >= 3 else digits
        return f"$***{visible}{cents}"

    def mask_account(match: re.Match) -> str:
        value = match.group(0)
        return "*" * max(len(value) - 4, 0) + value[-4:]

    masked = re.sub(r"\$[\d,]+(?:\.\d{1,2})?", mask_amount, masked)
    masked = re.sub(r"\b\d{8,}\b", mask_account, masked)
    return masked
