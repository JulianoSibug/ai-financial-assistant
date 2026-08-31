from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from backend import db
from backend.ingest.normalize import build_transactions
from backend.ingest.parse_csv import RawTransaction
from backend.ingest.reconcile import reconcile_file
from backend.models import Transaction


def _tx(desc: str, amount: Decimal) -> Transaction:
    raw = RawTransaction(date=date(2026, 8, 1), description=desc, amount=amount)
    return build_transactions([raw], account="checking", source_file="statement.csv", extraction_method="csv")[0]


def _setup_file(
    db_path: Path,
    transactions: list[Transaction],
    *,
    opening: Decimal | None = None,
    closing: Decimal | None = None,
    total_debits: Decimal | None = None,
    total_credits: Decimal | None = None,
) -> int:
    file_id = db.insert_file(
        db_path, path="/tmp/statement.csv", filename="statement.csv", size_bytes=1,
        mtime=0.0, sha256="hash", file_type="csv",
    )
    db.insert_transactions(db_path, file_id, transactions)
    db.set_file_statement_balances(
        db_path,
        file_id,
        opening_cents=db.to_cents(opening) if opening is not None else None,
        closing_cents=db.to_cents(closing) if closing is not None else None,
        total_debits_cents=db.to_cents(total_debits) if total_debits is not None else None,
        total_credits_cents=db.to_cents(total_credits) if total_credits is not None else None,
    )
    return file_id


def test_reconcile_ok_when_balances_match(db_path: Path) -> None:
    txs = [_tx("A", Decimal("-100.00")), _tx("B", Decimal("-50.00"))]
    file_id = _setup_file(db_path, txs, opening=Decimal("1000.00"), closing=Decimal("850.00"))

    status = reconcile_file(db_path, file_id)

    assert status == "ok"


def test_reconcile_warns_on_intentional_mismatch(db_path: Path) -> None:
    """A fixture deliberately engineered so the statement's claimed closing
    balance does NOT match what the parsed transactions sum to. The warning
    must fire -- this is the single most important correctness feature."""
    txs = [_tx("A", Decimal("-100.00")), _tx("B", Decimal("-50.00"))]
    file_id = _setup_file(db_path, txs, opening=Decimal("1000.00"), closing=Decimal("500.00"))

    status = reconcile_file(db_path, file_id)

    assert status == "warning"
    warnings = db.get_reconciliation_warnings(db_path)
    assert len(warnings) == 1
    assert warnings[0]["filename"] == "statement.csv"
    assert warnings[0]["delta_cents"] == db.to_cents(Decimal("500.00")) - db.to_cents(Decimal("850.00"))


def test_reconcile_not_applicable_when_no_balance_info(db_path: Path) -> None:
    txs = [_tx("A", Decimal("-20.00"))]
    file_id = _setup_file(db_path, txs)

    status = reconcile_file(db_path, file_id)

    assert status == "not_applicable"
    # not_applicable is a quiet note, not a failure -- but it must still be
    # visible/queryable rather than silently disappearing.
    rows = db.get_reconciliation_warnings(db_path)
    assert len(rows) == 1
    assert rows[0]["status"] == "not_applicable"


def test_reconcile_ok_with_total_debits_and_credits(db_path: Path) -> None:
    txs = [_tx("A", Decimal("-100.00")), _tx("B", Decimal("200.00"))]
    file_id = _setup_file(db_path, txs, total_debits=Decimal("100.00"), total_credits=Decimal("200.00"))

    status = reconcile_file(db_path, file_id)

    assert status == "ok"


def test_reconcile_warns_when_totals_dont_match(db_path: Path) -> None:
    txs = [_tx("A", Decimal("-100.00")), _tx("B", Decimal("200.00"))]
    file_id = _setup_file(db_path, txs, total_debits=Decimal("999.00"), total_credits=Decimal("200.00"))

    status = reconcile_file(db_path, file_id)

    assert status == "warning"
