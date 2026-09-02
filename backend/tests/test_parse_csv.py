from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from backend.ingest.parse_csv import parse_csv_file, parse_date_str, parse_money


def test_parse_money_plain() -> None:
    assert parse_money("42.10") == Decimal("42.10")


def test_parse_money_dollar_and_commas() -> None:
    assert parse_money("$1,234.56") == Decimal("1234.56")


def test_parse_money_negative_dollar() -> None:
    assert parse_money("-$1,234.56") == Decimal("-1234.56")


def test_parse_money_parenthesized_is_negative() -> None:
    assert parse_money("(45.00)") == Decimal("-45.00")
    assert parse_money("($1,200.00)") == Decimal("-1200.00")


def test_parse_money_trailing_minus() -> None:
    assert parse_money("45.00-") == Decimal("-45.00")


def test_parse_money_blank_is_none() -> None:
    assert parse_money("") is None
    assert parse_money(None) is None


def test_parse_date_common_formats() -> None:
    assert parse_date_str("08/15/2026").isoformat() == "2026-08-15"
    assert parse_date_str("2026-08-15").isoformat() == "2026-08-15"


def test_single_signed_amount_column(tmp_path: Path) -> None:
    csv_text = (
        "Transaction Date,Description,Amount\n"
        "08/01/2026,STARBUCKS #4471,-4.75\n"
        "08/02/2026,PAYCHECK DEPOSIT,1500.00\n"
        "08/03/2026,AMAZON MARKETPLACE,-42.10\n"
    )
    path = tmp_path / "single_amount.csv"
    path.write_text(csv_text)

    result = parse_csv_file(path)

    assert len(result.transactions) == 3
    amounts = [t.amount for t in result.transactions]
    assert amounts == [Decimal("-4.75"), Decimal("1500.00"), Decimal("-42.10")]


def test_separate_debit_credit_columns(tmp_path: Path) -> None:
    csv_text = (
        "Posting Date,Payee,Debit,Credit\n"
        "08/01/2026,STARBUCKS #4471,4.75,\n"
        "08/02/2026,PAYCHECK DEPOSIT,,1500.00\n"
    )
    path = tmp_path / "debit_credit.csv"
    path.write_text(csv_text)

    result = parse_csv_file(path)

    assert len(result.transactions) == 2
    # Debit column values are money OUT -> negative. Credit -> positive.
    assert result.transactions[0].amount == Decimal("-4.75")
    assert result.transactions[1].amount == Decimal("1500.00")


def test_parenthesized_negatives_in_amount_column(tmp_path: Path) -> None:
    csv_text = (
        "Date,Description,Amount\n"
        "08/05/2026,GYM MEMBERSHIP,(45.00)\n"
        "08/06/2026,REFUND,45.00\n"
    )
    path = tmp_path / "parens.csv"
    path.write_text(csv_text)

    result = parse_csv_file(path)

    assert result.transactions[0].amount == Decimal("-45.00")
    assert result.transactions[1].amount == Decimal("45.00")


def test_opening_and_closing_balance_inferred_from_balance_column(tmp_path: Path) -> None:
    csv_text = (
        "Date,Description,Amount,Balance\n"
        "08/01/2026,OPENING TX,-100.00,900.00\n"
        "08/02/2026,SECOND TX,-50.00,850.00\n"
    )
    path = tmp_path / "with_balance.csv"
    path.write_text(csv_text)

    result = parse_csv_file(path)

    # first balance (900) minus first amount (-100) = 1000 opening balance
    assert result.opening_balance == Decimal("1000.00")
    assert result.closing_balance == Decimal("850.00")


def test_credit_card_export_inverts_unsigned_purchase_amounts(tmp_path: Path) -> None:
    """Discover-style CSVs print purchases positive (money owed increases)
    and payments/credits negative -- the opposite of Ledger's convention,
    where a purchase must be negative (money out). Detected via issuer name
    in the filename here."""
    csv_text = (
        "Trans. Date,Post Date,Description,Amount,Category\n"
        "09/11/2024,09/11/2024,APPLE.COM/BILL,9.99,Merchandise\n"
        "09/29/2024,09/29/2024,INTERNET PAYMENT - THANK YOU,-10.73,Payments and Credits\n"
    )
    path = tmp_path / "Discover-AllAvailable-20260902.csv"
    path.write_text(csv_text)

    result = parse_csv_file(path)

    assert result.transactions[0].amount == Decimal("-9.99")  # purchase -> money out
    assert result.transactions[1].amount == Decimal("10.73")  # payment -> money in


def test_credit_card_export_detected_via_category_column_without_issuer_name(tmp_path: Path) -> None:
    csv_text = (
        "Date,Description,Amount,Category\n"
        "07/01/2026,SOME STORE,42.00,Merchandise\n"
    )
    path = tmp_path / "card_export.csv"  # no recognizable issuer name
    path.write_text(csv_text)

    result = parse_csv_file(path)

    assert result.transactions[0].amount == Decimal("-42.00")


def test_checking_account_export_amount_sign_not_inverted(tmp_path: Path) -> None:
    """A plain checking-account CSV (no Category column, no issuer name in
    the filename) must keep its amount sign as printed."""
    csv_text = (
        "Date,Description,Amount\n"
        "07/01/2026,PAYCHECK,1500.00\n"
        "07/02/2026,GROCERY STORE,-60.00\n"
    )
    path = tmp_path / "checking_export.csv"
    path.write_text(csv_text)

    result = parse_csv_file(path)

    assert result.transactions[0].amount == Decimal("1500.00")
    assert result.transactions[1].amount == Decimal("-60.00")
