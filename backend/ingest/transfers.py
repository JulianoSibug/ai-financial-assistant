"""Deterministic, LLM-independent detection of obvious inter-account
transfers -- credit card payments, transfers between the person's own
checking/savings/shares -- so these don't show up as spending even before
LLM categorization has run (or if it never runs, e.g. no LLM configured).

This is a *safety net*, not a replacement for categorization. It only
flags patterns unambiguous enough to trust without judgment; anything less
clear-cut is left for the LLM categorization stage (backend/llm/categorize.py),
which sets the same is_transfer flag with more context (merchant, amount,
date) and a fixed taxonomy. A transaction this module flags is marked
category_source="rule" and is treated as settled -- it will not be re-sent
to the LLM (see db.get_uncategorized_transactions), the same way a manual
or cached classification is.

Deliberately conservative: patterns are drawn only from constructs observed
in real statement text during development, not guessed broadly. In
particular, a generic "Paid To -" prefix is NOT treated as a transfer on
its own -- the same bank uses it for real spending too (e.g. "Paid To -
Planet Fitness"), so only specific, unambiguous payment/transfer language
is matched.

Matching is done on a whitespace-COLLAPSED copy of the description, not a
spaced regex -- pdfplumber's text extraction has been observed injecting a
stray space at an unpredictable position inside a word ("E-Payment" ->
"E-P ayment" in one place in the same document that reads fine elsewhere),
so tolerating one specific gap isn't enough; removing whitespace entirely
before matching sidesteps the problem regardless of where it lands.
"""
from __future__ import annotations

import re


def _collapse(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


_INTERNAL_TRANSFER_RE = re.compile(
    r"transfer(?:to|from)(?:checking|savings|shares|share|moneymarket)"
)

# Card issuer name co-occurring with "e-payment" is what distinguishes a
# credit-card bill payment ("Paid To - Discover E-Payment") from ordinary
# spending that happens to share the "Paid To -" prefix ("Paid To - Planet
# Fitness"). "citi" deliberately excludes "citizens" (a different, unrelated
# bank whose name also contains that substring).
_CARD_ISSUERS = ("discover", "chase", "amex", "americanexpress", "citi", "capitalone", "barclay", "synchrony")


def _is_card_payment(collapsed: str) -> bool:
    if "epayment" not in collapsed and "e-payment" not in collapsed:
        return False
    if "citizens" in collapsed:
        return False
    return any(issuer in collapsed for issuer in _CARD_ISSUERS)


def _is_card_payment_confirmation(collapsed: str) -> bool:
    # The credit card statement's own side of the same payment, e.g.
    # "INTERNET PAYMENT - THANK YOU" -- appears as a credit there, not the
    # bank account's side.
    return "internetpayment" in collapsed and "thankyou" in collapsed


def looks_like_transfer(description: str) -> bool:
    """True only for patterns confident enough to skip LLM review entirely.
    False does not mean "not a transfer" -- it means "let the LLM decide,"
    which is the default for anything not matched here."""
    collapsed = _collapse(description)
    return bool(
        _INTERNAL_TRANSFER_RE.search(collapsed)
        or _is_card_payment(collapsed)
        or _is_card_payment_confirmation(collapsed)
    )
