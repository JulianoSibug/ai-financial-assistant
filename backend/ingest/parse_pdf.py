"""Stage 2 (PDF): pdfplumber text extraction + regex line parser, with an
LLM-extraction fallback for pages the regex can't handle.

Also extracts statement-declared balance figures (opening/closing/total
debits/credits) via label regexes, for stage 5 (reconcile.py) to check
parsed transactions against later.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

import pdfplumber

from backend.ingest.parse_csv import ParsedStatement, RawTransaction, parse_money

# Date: month/day with an optional year, either slash- or hyphen-separated
# ("07/02/2026", "08-05-26", "07/02" with no year at all -- real statements
# use all three; a missing year is filled in from _guess_statement_year()).
_PDF_LINE_RE = re.compile(
    r"^\s*(?P<month>\d{1,2})[/-](?P<day>\d{1,2})(?:[/-](?P<year>\d{2,4}))?\s+"
    r"(?P<description>.+?)\s+"
    r"(?P<amount>\(?-?\$?[\d,]+\.\d{2}\)?-?)"
    r"(?:\s+(?P<balance>\(?-?\$?[\d,]+\.\d{2}\)?-?))?\s*$"
)
_LOOSE_DATE_LINE_RE = re.compile(r"^\s*\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\s+\S")

# A date elsewhere in the document (statement period, account summary, ...)
# that does carry a year -- used to fill in year-less transaction dates.
_YEAR_IN_DATE_RE = re.compile(r"\d{1,2}[/-]\d{1,2}[/-](\d{2,4})\b")
_YEAR_4_RE = re.compile(r"\b(20\d{2})\b")

# Many credit-card statements print purchases as plain positive amounts
# ("$4.92") under a "Purchases" heading and only sign payments/credits
# explicitly -- a purchase is still money out, so an unsigned amount under
# a "Purchases" heading gets negated. Anything already signed or
# parenthesized is always trusted as printed.
_PURCHASE_SECTION_RE = re.compile(r"purchases", re.IGNORECASE)
_PAYMENT_SECTION_RE = re.compile(r"payments?\s*(?:and)?\s*credits", re.IGNORECASE)

# "07-22  Beginning Balance  21.54" matches DATE+DESCRIPTION+AMOUNT shape but
# isn't a transaction -- it's a running-balance marker some statements print
# inline in the transaction table. Excluded outright rather than ingested as
# a fake movement of money. Matched with whitespace collapsed out entirely,
# since pdfplumber's text extraction sometimes injects a stray space
# mid-word (observed as literal "Ending B alance" from a real statement).
_BALANCE_MARKER_WORDS = {
    "beginningbalance", "endingbalance", "openingbalance",
    "closingbalance", "previousbalance", "newbalance",
}


def _is_balance_marker(description: str) -> bool:
    collapsed = re.sub(r"\s+", "", description).lower()
    return collapsed in _BALANCE_MARKER_WORDS

MIN_REGEX_MATCHES = 5
MIN_LOOSE_DATE_LINES = 3


def extract_pages_text(path: Path) -> list[str]:
    with pdfplumber.open(path) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def looks_like_transaction_page(page_text: str) -> bool:
    """A loose, permissive check (any line starting with a date) used only to
    decide whether a page's low regex yield means 'no transactions here' or
    'transactions the strict parser is missing'."""
    lines = page_text.splitlines()
    return sum(1 for line in lines if _LOOSE_DATE_LINE_RE.match(line)) >= MIN_LOOSE_DATE_LINES


def guess_statement_year(full_text: str) -> int | None:
    """Best-effort: statements that omit the year on each transaction line
    almost always print a full date (statement period, account summary...)
    somewhere else on the page."""
    m = _YEAR_IN_DATE_RE.search(full_text)
    if m:
        year_str = m.group(1)
        return 2000 + int(year_str) if len(year_str) == 2 else int(year_str)
    m = _YEAR_4_RE.search(full_text)
    return int(m.group(1)) if m else None


def parse_page_regex(page_text: str, year_hint: int | None = None) -> list[RawTransaction]:
    transactions: list[RawTransaction] = []
    treat_unsigned_as_negative = False

    for line in page_text.splitlines():
        m = _PDF_LINE_RE.match(line)
        if not m:
            # Not a transaction line -- but it might be a section header that
            # changes how to interpret unsigned amounts on the lines after it.
            if _PURCHASE_SECTION_RE.search(line):
                treat_unsigned_as_negative = True
            elif _PAYMENT_SECTION_RE.search(line):
                treat_unsigned_as_negative = False
            continue

        if _is_balance_marker(m.group("description")):
            continue

        month, day = int(m.group("month")), int(m.group("day"))
        year_str = m.group("year")
        if year_str:
            year = int(year_str)
            if year < 100:
                year += 2000
        elif year_hint is not None:
            year = year_hint
        else:
            continue  # no year on the line and nothing to infer from

        try:
            tx_date = date(year, month, day)
        except ValueError:
            continue

        raw_amount = m.group("amount")
        amount = parse_money(raw_amount)
        if amount is None:
            continue
        if treat_unsigned_as_negative and amount > 0 and "-" not in raw_amount and "(" not in raw_amount:
            amount = -amount

        transactions.append(
            RawTransaction(date=tx_date, description=m.group("description").strip(), amount=amount)
        )
    return transactions


@dataclass
class PageResult:
    page_number: int
    transactions: list[RawTransaction]
    extraction_method: str  # 'regex' | 'llm'


def parse_pdf_file(
    path: Path,
    llm_fallback: Callable[[str], list[RawTransaction]] | None = None,
) -> tuple[ParsedStatement, list[PageResult]]:
    """Returns the combined ParsedStatement plus a per-page breakdown so the
    caller can tag which rows came from the LLM fallback (extraction_method)."""
    pages = extract_pages_text(path)
    full_text = "\n".join(pages)
    year_hint = guess_statement_year(full_text)

    result = ParsedStatement()
    page_results: list[PageResult] = []

    for i, page_text in enumerate(pages, start=1):
        regex_matches = parse_page_regex(page_text, year_hint=year_hint)
        if len(regex_matches) >= MIN_REGEX_MATCHES or not looks_like_transaction_page(page_text):
            page_results.append(PageResult(i, regex_matches, "regex"))
            result.transactions.extend(regex_matches)
            continue

        if llm_fallback is not None:
            llm_matches = llm_fallback(page_text)
            page_results.append(PageResult(i, llm_matches, "llm"))
            result.transactions.extend(llm_matches)
        else:
            page_results.append(PageResult(i, regex_matches, "regex"))
            result.transactions.extend(regex_matches)

    _extract_balance_hints(full_text, result)
    return result, page_results


_MONEY_TOKEN = r"([\-\(]?\$?[\d,]+\.\d{2}\)?-?)"
_BALANCE_LABELS = {
    "opening_balance": re.compile(rf"(?:beginning|opening|previous)\s+balance\D{{0,15}}{_MONEY_TOKEN}", re.IGNORECASE),
    "closing_balance": re.compile(rf"(?:ending|closing|new)\s+balance\D{{0,15}}{_MONEY_TOKEN}", re.IGNORECASE),
    "total_debits": re.compile(rf"total\s+(?:debits|withdrawals|payments|purchases)\D{{0,15}}{_MONEY_TOKEN}", re.IGNORECASE),
    "total_credits": re.compile(rf"total\s+(?:credits|deposits)\D{{0,15}}{_MONEY_TOKEN}", re.IGNORECASE),
}


def _extract_balance_hints(full_text: str, result: ParsedStatement) -> None:
    for field_name, pattern in _BALANCE_LABELS.items():
        m = pattern.search(full_text)
        if m:
            setattr(result, field_name, parse_money(m.group(1)))
