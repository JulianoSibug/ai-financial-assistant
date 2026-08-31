"""PII redaction: strips account/card numbers, SSNs, and addresses from any
text before it is sent to an LLM. Merchant names and amounts must pass
through untouched -- the categorization and PDF-extraction prompts need
those to do their job.
"""
from __future__ import annotations

import re

REDACTED = "[REDACTED]"

_SSN_HYPHEN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_SSN_SPACE_RE = re.compile(r"\b\d{3}\s\d{2}\s\d{4}\b")

# Grouped card numbers: 4-4-4-4 (Visa/Mastercard/Discover) or 4-6-5 (Amex).
_CARD_GROUPED_RE = re.compile(r"\b\d{4}[- ]\d{4,6}[- ]\d{4,5}(?:[- ]\d{4})?\b")

# "Account #1234567890", "Acct Number: 1234-5678-90", "account ending in 4321"
_ACCOUNT_LABELED_RE = re.compile(
    r"\b(?:account|acct)\.?\s*(?:number|no\.?|#)?\s*(?:ending\s+in\s*)?[:#]?\s*[\d][\d\- ]{3,}\d\b",
    re.IGNORECASE,
)

# Generic bare digit run, 8-19 digits: long enough to be an account/card/SSN
# number; commas and decimal points in dollar amounts already break up any
# contiguous digit run, so "$12,345,678.90" is never at risk here.
_GENERIC_DIGIT_RUN_RE = re.compile(r"\b\d{8,19}\b")

_STREET_SUFFIXES = (
    r"street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|lane|ln|court|ct|"
    r"way|place|pl|terrace|ter|circle|cir|highway|hwy|parkway|pkwy"
)
# "123 Main St, Anytown, CA 12345" / "123 Main St Apt 4B, Anytown, CA 12345"
_ADDRESS_RE = re.compile(
    rf"\b\d{{1,6}}\s+[A-Za-z0-9.'\s]{{1,40}}?\b(?:{_STREET_SUFFIXES})\b\.?"
    rf"(?:[,\s]+[A-Za-z.'\s]{{1,30}}){{0,2}}[,\s]+[A-Z]{{2}}\s+\d{{5}}(?:-\d{{4}})?\b",
    re.IGNORECASE,
)


def redact_text(text: str) -> str:
    """Most specific patterns run first (SSN, grouped cards, addresses); the
    generic digit-run catch-all runs last to mop up whatever those miss."""
    result = text
    result = _ADDRESS_RE.sub(REDACTED, result)
    result = _SSN_HYPHEN_RE.sub(REDACTED, result)
    result = _SSN_SPACE_RE.sub(REDACTED, result)
    result = _CARD_GROUPED_RE.sub(REDACTED, result)
    result = _ACCOUNT_LABELED_RE.sub(REDACTED, result)
    result = _GENERIC_DIGIT_RUN_RE.sub(REDACTED, result)
    return result
