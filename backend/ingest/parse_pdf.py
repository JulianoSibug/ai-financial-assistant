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
_MONEY_TOKEN_RE = r"\(?-?\$?[\d,]+\.\d{2}\)?\s?-?"  # trailing minus may have a
# space before it ("75.00 -") as well as none ("700.00-") -- some statements
# print both within the same file.
_PDF_LINE_RE = re.compile(
    r"^\s*(?P<month>\d{1,2})[/-](?P<day>\d{1,2})(?:[/-](?P<year>\d{2,4}))?\s+"
    r"(?P<description>.+?)\s+"
    rf"(?P<amount>{_MONEY_TOKEN_RE})"
    rf"(?:\s+(?P<balance>{_MONEY_TOKEN_RE}))?\s*$"
)
_LOOSE_DATE_LINE_RE = re.compile(r"^\s*\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\s+\S")
_ENDS_WITH_MONEY_RE = re.compile(rf"{_MONEY_TOKEN_RE}\s*$")


def _merge_wrapped_lines(lines: list[str]) -> list[str]:
    """A long merchant description wraps to a second physical line before
    the amount, e.g. "...Bjs Wholesale #0 13053 Fairfax" / "VA 12.34- 187.17"
    -- neither line alone looks like a complete transaction, so the whole
    row is silently dropped rather than misread. Detected as: a date-led
    line with no trailing amount, immediately followed by a line that
    doesn't itself start a new date-led entry but does end in one -- merged
    into a single logical line before the main parse."""
    merged: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if (
            i + 1 < len(lines)
            and _LOOSE_DATE_LINE_RE.match(line)
            and not _ENDS_WITH_MONEY_RE.search(line)
            and not _LOOSE_DATE_LINE_RE.match(lines[i + 1])
            and _ENDS_WITH_MONEY_RE.search(lines[i + 1])
        ):
            merged.append(f"{line.rstrip()} {lines[i + 1].strip()}")
            i += 2
            continue
        merged.append(line)
        i += 1
    return merged


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

# pdfplumber's text extraction has been observed injecting a stray space at
# an unpredictable position inside a word on real statements -- "Balance" ->
# "B alance" in one place, "Ending" -> "End ing" in another, in the SAME
# document. Word-presence checks below collapse whitespace out entirely
# before comparing; where a word must be matched inline (to find a nearby
# dollar figure), _loose() builds a regex tolerating an optional space
# between any two of its letters.


def _loose(word: str) -> str:
    return r"\s?".join(list(word))


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


# Some statements print an "Items Paid" recap table after each sub-account's
# real transaction listing -- a two-column summary of the same items already
# counted above, not new transactions. Flattened to plain text by pdfplumber,
# a two-column row like "08-03 ACH 3.00  07-23 POS 33.00" reads as one line
# with an extra embedded date+description in the middle, which the regex
# line parser misreads as a single transaction with the WRONG (second
# column's) amount -- fabricating a real dollar figure, not just duplicating
# one. Suppressed entirely until the next sub-account's real table resumes
# (signaled by its "Beginning Balance" line reappearing).
_ITEMS_PAID_RE = re.compile(r"items\s+paid", re.IGNORECASE)


def _is_beginning_balance_line(line: str) -> bool:
    return "beginningbalance" in _collapse_ws(line)


# "07-22  Beginning Balance  21.54" matches DATE+DESCRIPTION+AMOUNT shape but
# isn't a transaction -- it's a running-balance marker some statements print
# inline in the transaction table. Excluded outright rather than ingested as
# a fake movement of money.
_BALANCE_MARKER_WORDS = {
    "beginningbalance", "endingbalance", "openingbalance",
    "closingbalance", "previousbalance", "newbalance",
}


def _is_balance_marker(description: str) -> bool:
    collapsed = _collapse_ws(description)
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
    in_items_paid_recap = False

    for line in _merge_wrapped_lines(page_text.splitlines()):
        if _ITEMS_PAID_RE.search(line):
            in_items_paid_recap = True
            continue
        if in_items_paid_recap:
            if _is_beginning_balance_line(line):
                in_items_paid_recap = False
            else:
                continue

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
    flagged: bool = False  # looked like a transaction page but nothing was extracted


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
            if len(llm_matches) >= len(regex_matches):
                page_results.append(PageResult(i, llm_matches, "llm", flagged=len(llm_matches) == 0))
                result.transactions.extend(llm_matches)
            else:
                # The fallback returned fewer transactions than the regex
                # parser already found on this page -- including zero, e.g.
                # if the LLM isn't actually available and the call failed
                # silently. Keep the regex result rather than discard real,
                # already-parsed data for nothing.
                page_results.append(PageResult(i, regex_matches, "regex", flagged=len(regex_matches) == 0))
                result.transactions.extend(regex_matches)
        else:
            page_results.append(PageResult(i, regex_matches, "regex", flagged=len(regex_matches) == 0))
            result.transactions.extend(regex_matches)

    _extract_balance_hints(full_text, result)
    return result, page_results


def detect_low_extraction(page_results: list[PageResult]) -> tuple[bool, str | None]:
    """Signals when one or more pages looked like they contained transactions
    but extraction (regex and LLM fallback) came up with none -- distinct from
    reconciliation, which only fires when there's a checkable balance figure."""
    flagged_pages = [pr.page_number for pr in page_results if pr.flagged]
    if not flagged_pages:
        return False, None
    pages_str = ", ".join(str(p) for p in flagged_pages)
    plural = "s" if len(flagged_pages) > 1 else ""
    return True, f"Page{plural} {pages_str} look{'' if plural else 's'} like they contain transactions but none were extracted."


_MONEY_TOKEN = r"([\-\(]?\$?[\d,]+\.\d{2}\)?-?)"
# Every word here runs through _loose() -- observed on real statements as
# "Balance" -> "B alance" in one sub-account's Ending line and "Ending" ->
# "End ing" in another, in the SAME document. Missing either one doesn't
# misread the figure, it drops the whole match, which is worse: a wrong
# balance-hint total would at least look plausible, a partial one produces a
# large, confusing reconciliation delta with no obvious cause.
_BAL = _loose("balance")
_BALANCE_LABELS = {
    "opening_balance": re.compile(
        rf"(?:{_loose('beginning')}|{_loose('opening')}|{_loose('previous')})\s+{_BAL}\D{{0,15}}{_MONEY_TOKEN}",
        re.IGNORECASE,
    ),
    "closing_balance": re.compile(
        rf"(?:{_loose('ending')}|{_loose('closing')}|{_loose('new')})\s+{_BAL}\D{{0,15}}{_MONEY_TOKEN}",
        re.IGNORECASE,
    ),
    "total_debits": re.compile(
        rf"{_loose('total')}\s+(?:{_loose('debits')}|{_loose('withdrawals')}|{_loose('payments')}|{_loose('purchases')})"
        rf"\D{{0,15}}{_MONEY_TOKEN}",
        re.IGNORECASE,
    ),
    "total_credits": re.compile(
        rf"{_loose('total')}\s+(?:{_loose('credits')}|{_loose('deposits')})\D{{0,15}}{_MONEY_TOKEN}",
        re.IGNORECASE,
    ),
}


def _extract_balance_hints(full_text: str, result: ParsedStatement) -> None:
    """A single PDF can contain multiple sub-accounts (e.g. checking +
    savings on one statement), each with its own "Beginning Balance" /
    "Ending Balance" pair -- summing every match found gives the correct
    file-wide total to check the file-wide transaction sum against, rather
    than comparing against just one sub-account's balance (which is what
    taking only the first match would do)."""
    for field_name, pattern in _BALANCE_LABELS.items():
        matches = [parse_money(m.group(1)) for m in pattern.finditer(full_text)]
        values = [v for v in matches if v is not None]
        if values:
            setattr(result, field_name, sum(values[1:], values[0]))
