from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from backend.ingest.parse_csv import ParsedStatement, RawTransaction
from backend.ingest.parse_pdf import _extract_balance_hints, guess_statement_year, parse_page_regex, parse_pdf_file
from backend.tests.fixtures.build_fixtures import FixtureTransaction, make_pdf_statement


def test_parse_page_regex_extracts_date_description_amount() -> None:
    page_text = (
        "Statement of Account\n"
        "Beginning balance: $1000.00\n"
        "08/01/2026  STARBUCKS #4471  -4.75\n"
        "08/02/2026  PAYCHECK DEPOSIT  1500.00\n"
    )
    transactions = parse_page_regex(page_text)
    assert len(transactions) == 2
    assert transactions[0].date == date(2026, 8, 1)
    assert transactions[0].amount == Decimal("-4.75")
    assert transactions[0].description == "STARBUCKS #4471"


def test_parse_pdf_file_generated_fixture(tmp_path: Path) -> None:
    txs = [
        FixtureTransaction(date(2026, 8, 1), "STARBUCKS #4471", Decimal("-4.75")),
        FixtureTransaction(date(2026, 8, 3), "PAYCHECK DEPOSIT", Decimal("1500.00")),
        FixtureTransaction(date(2026, 8, 5), "WHOLE FOODS MARKET", Decimal("-86.42")),
        FixtureTransaction(date(2026, 8, 10), "SHELL OIL AUSTIN TX", Decimal("-38.20")),
        FixtureTransaction(date(2026, 8, 15), "NETFLIX.COM", Decimal("-15.49")),
        FixtureTransaction(date(2026, 8, 20), "RENT PAYMENT", Decimal("-1200.00")),
    ]
    pdf_path = tmp_path / "statement.pdf"
    make_pdf_statement(pdf_path, txs, opening_balance=Decimal("1000.00"))

    parsed, page_results = parse_pdf_file(pdf_path)

    assert len(parsed.transactions) == 6
    assert parsed.opening_balance == Decimal("1000.00")
    assert parsed.closing_balance == Decimal("1000.00") + sum((t.amount for t in txs), Decimal("0"))
    assert page_results[0].extraction_method == "regex"


def test_balance_hints_sum_across_multiple_sub_accounts_in_one_pdf() -> None:
    """A single statement PDF can contain several sub-accounts (checking +
    savings), each with its own Beginning/Ending Balance pair. The file-wide
    hint used for reconciliation must be the SUM of every sub-account's
    balance, not just the first one found -- otherwise reconciliation
    compares the whole file's transaction sum against only one sub-account's
    balance and reports a spurious mismatch."""
    full_text = (
        "EveryDay Checking - 1111111\n"
        "07-22 Beginning Balance 100.00\n"
        "07-23 Groceries -20.00\n"
        "07-31 Ending Balance 80.00\n"
        "Savings - 2222222\n"
        "07-22 Beginning Balance 500.00\n"
        "07-25 Interest 5.00\n"
        "07-31 Ending Balance 505.00\n"
    )
    result = ParsedStatement()
    _extract_balance_hints(full_text, result)
    assert result.opening_balance == Decimal("600.00")  # 100 + 500
    assert result.closing_balance == Decimal("585.00")  # 80 + 505


def test_parse_pdf_file_falls_back_to_llm_on_sparse_page(tmp_path: Path) -> None:
    """A page pdfplumber can extract text from, but where the strict regex
    can't find >=5 transactions, should trigger the LLM fallback callback."""
    pdf_path = tmp_path / "sparse.pdf"
    # Only 2 well-formed transaction lines, but several loose date-led lines
    # so the page still "looks like" it has transactions worth extracting.
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    _, height = letter
    y = height - 72
    lines = [
        "08/01/2026  ONE  -1.00",
        "08/02/2026  TWO  -2.00",
        "08/03/2026  malformed line without a clean amount at end abc",
        "08/04/2026  another malformed line xyz",
        "08/05/2026  yet another one",
    ]
    for line in lines:
        c.drawString(72, y, line)
        y -= 14
    c.save()

    calls: list[str] = []

    def fake_llm_fallback(page_text: str) -> list:
        calls.append(page_text)
        return [
            RawTransaction(date=date(2026, 8, 1), description="ONE", amount=Decimal("-1.00")),
            RawTransaction(date=date(2026, 8, 2), description="TWO", amount=Decimal("-2.00")),
            RawTransaction(date=date(2026, 8, 3), description="THREE", amount=Decimal("-3.00")),
        ]

    parsed, page_results = parse_pdf_file(pdf_path, llm_fallback=fake_llm_fallback)

    assert len(calls) == 1  # fallback was invoked exactly once, for the one page
    assert page_results[0].extraction_method == "llm"
    assert len(parsed.transactions) == 3


def test_llm_fallback_failure_does_not_discard_regexs_own_matches(tmp_path: Path) -> None:
    """If the fallback returns fewer transactions than the regex parser
    already found on that page -- including zero, e.g. because the LLM
    isn't actually available and the call just failed -- the regex results
    must be kept, not thrown away for nothing."""
    pdf_path = tmp_path / "sparse2.pdf"
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    _, height = letter
    y = height - 72
    lines = [
        "08/01/2026  ONE  -1.00",
        "08/02/2026  TWO  -2.00",
        "08/03/2026  malformed line without a clean amount at end abc",
        "08/04/2026  another malformed line xyz",
        "08/05/2026  yet another one",
    ]
    for line in lines:
        c.drawString(72, y, line)
        y -= 14
    c.save()

    def failing_llm_fallback(page_text: str) -> list:
        return []  # simulates the LLM being unavailable

    parsed, page_results = parse_pdf_file(pdf_path, llm_fallback=failing_llm_fallback)

    assert page_results[0].extraction_method == "regex"
    assert len(parsed.transactions) == 2  # ONE and TWO, still recovered by regex


# --- regression tests from real-world statement formats ---


def test_hyphenated_date_with_two_digit_year() -> None:
    page_text = "08-05-26  Intl Transaction Fee  0.25\n"
    transactions = parse_page_regex(page_text)
    assert len(transactions) == 1
    assert transactions[0].date == date(2026, 8, 5)


def test_year_less_date_uses_year_hint() -> None:
    page_text = "07/02  WALMART STORE 02015 FAIRFAX VA  4.92\n"
    transactions = parse_page_regex(page_text, year_hint=2026)
    assert len(transactions) == 1
    assert transactions[0].date == date(2026, 7, 2)


def test_year_less_date_dropped_without_a_hint() -> None:
    page_text = "07/02  WALMART STORE 02015 FAIRFAX VA  4.92\n"
    assert parse_page_regex(page_text) == []


def test_trailing_minus_with_space_before_it() -> None:
    """Some statements print the trailing minus flush against the amount
    ("700.00-") and others with a space before it ("75.00 -") -- sometimes
    both within the same file. A space there must not cause the following
    balance figure to be mistaken for the amount."""
    page_text = "04-03 Transfer To Checking 75.00 - 1,705.98\n"
    transactions = parse_page_regex(page_text, year_hint=2026)
    assert len(transactions) == 1
    assert transactions[0].amount == Decimal("-75.00")


def test_guess_statement_year_from_two_digit_date_in_header() -> None:
    full_text = "Statement Period\n07/22/26 - 08/21/26\nsome other text"
    assert guess_statement_year(full_text) == 2026


def test_guess_statement_year_from_four_digit_date_in_header() -> None:
    full_text = "Account Summary 07/05/2026 -08/04/2026"
    assert guess_statement_year(full_text) == 2026


def test_purchases_section_unsigned_amount_becomes_negative() -> None:
    page_text = (
        "TRANS.\n"
        "DATE PURCHASES MERCHANTCATEGORY AMOUNT\n"
        "07/02/2026 WALMART STORE 02015 FAIRFAX VA Merchandise 4.92\n"
    )
    transactions = parse_page_regex(page_text)
    assert len(transactions) == 1
    assert transactions[0].amount == Decimal("-4.92")


def test_payments_and_credits_section_keeps_explicit_sign() -> None:
    page_text = (
        "DATE PAYMENTSANDCREDITS AMOUNT\n"
        "07/10/2026 INTERNET PAYMENT - THANK YOU -1849.30\n"
    )
    transactions = parse_page_regex(page_text)
    assert len(transactions) == 1
    assert transactions[0].amount == Decimal("-1849.30")


def test_purchases_section_does_not_flip_already_signed_amount() -> None:
    """A signed or parenthesized amount is always trusted as printed, even
    under a Purchases heading, in case a statement ever mixes conventions."""
    page_text = (
        "DATE PURCHASES AMOUNT\n"
        "07/02/2026 REFUNDED ITEM -4.92\n"
    )
    transactions = parse_page_regex(page_text)
    assert transactions[0].amount == Decimal("-4.92")


def test_beginning_ending_balance_lines_excluded() -> None:
    page_text = (
        "07-22 Beginning Balance 21.54\n"
        "08-03 Transfer From Checking 10.00\n"
        "08-21 Ending Balance 31.54\n"
    )
    transactions = parse_page_regex(page_text, year_hint=2026)
    descriptions = [t.description for t in transactions]
    assert descriptions == ["Transfer From Checking"]


def test_wrapped_description_line_merged_before_parsing() -> None:
    """A long merchant name wraps to a second physical line before the
    amount appears -- neither line alone looks like a complete transaction,
    so without merging them first, the whole row is silently dropped."""
    page_text = (
        "06-09 POS Debit - Debit Card 3385 Transaction 06-08-26 Bjs Wholesale #0 13053 Fairfax\n"
        "VA 12.34- 187.17\n"
    )
    transactions = parse_page_regex(page_text, year_hint=2026)
    assert len(transactions) == 1
    assert transactions[0].amount == Decimal("-12.34")
    assert transactions[0].description.endswith("Fairfax VA")


def test_items_paid_recap_section_excluded() -> None:
    """An 'Items Paid' recap table repeats items already counted above, in a
    two-column layout that flattens into garbage when read line-by-line --
    it must be suppressed entirely, not parsed as new transactions."""
    page_text = (
        "07-22 Beginning Balance 100.00\n"
        "08-05 POS Debit Card Some Store 25.00- 75.00\n"
        "08-21 Ending Balance 75.00\n"
        "Items Paid\n"
        "Date Item Amount($) Date Item Amount($)\n"
        "08-03 A CH 3.00 07-23 P OS 33.00\n"
        "08-10 ACH 1,412.37 08-03 POS 49.40\n"
        "Savings - 2222222\n"
        "07-22 Beginning Balance 500.00\n"
        "08-21 Ending Balance 500.00\n"
    )
    transactions = parse_page_regex(page_text, year_hint=2026)
    descriptions = [t.description for t in transactions]
    assert descriptions == ["POS Debit Card Some Store"]


def test_balance_marker_excluded_even_with_ocr_injected_space() -> None:
    """Real-world pdfplumber extraction observed splitting 'Balance' into
    'B alance' -- the exclusion must survive that."""
    page_text = "08-21 Ending B alance 6.29\n"
    transactions = parse_page_regex(page_text, year_hint=2026)
    assert transactions == []
