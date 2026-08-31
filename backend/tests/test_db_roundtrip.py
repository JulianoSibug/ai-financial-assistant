from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from backend import db
from backend.models import Transaction


@pytest.mark.parametrize(
    "amount",
    [
        Decimal("0.10"),
        Decimal("-0.01"),
        Decimal("1234567.89"),
        Decimal("-1234567.89"),
        Decimal("0.00"),
        Decimal("100"),
    ],
)
def test_cents_roundtrip_exact(amount: Decimal) -> None:
    assert db.from_cents(db.to_cents(amount)) == amount.quantize(Decimal("0.01"))


def test_transaction_roundtrips_through_sqlite(db_path: Path) -> None:
    file_id = db.insert_file(
        db_path,
        path="/tmp/statement.csv",
        filename="statement.csv",
        size_bytes=100,
        mtime=0.0,
        sha256="deadbeef",
        file_type="csv",
    )

    tx = Transaction(
        id=db.make_transaction_id("checking", "2026-08-15", "STARBUCKS #4471", Decimal("-4.75")),
        date="2026-08-15",
        description="STARBUCKS #4471 SEATTLE WA",
        merchant="Starbucks",
        merchant_normalized="starbucks",
        amount=Decimal("-4.75"),
        account="checking",
        source_file="statement.csv",
        extraction_method="csv",
    )

    inserted = db.insert_transactions(db_path, file_id, [tx])
    assert inserted == 1

    fetched = db.get_transaction(db_path, tx.id)
    assert fetched is not None
    assert fetched.amount == Decimal("-4.75")
    assert isinstance(fetched.amount, Decimal)
    assert fetched.merchant == "Starbucks"
    assert fetched.category_source == "uncategorized"


def test_insert_transactions_dedups_on_id(db_path: Path) -> None:
    file_id = db.insert_file(
        db_path, path="/tmp/a.csv", filename="a.csv", size_bytes=1, mtime=0.0,
        sha256="hash-a", file_type="csv",
    )
    tx = Transaction(
        id=db.make_transaction_id("checking", "2026-08-01", "ACME", Decimal("-10.00")),
        date="2026-08-01", description="ACME", merchant="Acme", merchant_normalized="acme",
        amount=Decimal("-10.00"), account="checking", source_file="a.csv", extraction_method="csv",
    )
    first = db.insert_transactions(db_path, file_id, [tx])
    second = db.insert_transactions(db_path, file_id, [tx])
    assert first == 1
    assert second == 0
    assert len(db.get_all_transactions(db_path)) == 1


def test_manual_override_does_not_get_clobbered_by_reingest(db_path: Path) -> None:
    file_id = db.insert_file(
        db_path, path="/tmp/b.csv", filename="b.csv", size_bytes=1, mtime=0.0,
        sha256="hash-b", file_type="csv",
    )
    tx = Transaction(
        id=db.make_transaction_id("checking", "2026-08-01", "WIDGET CO", Decimal("-20.00")),
        date="2026-08-01", description="WIDGET CO", merchant="Widget Co",
        merchant_normalized="widget co", amount=Decimal("-20.00"), account="checking",
        source_file="b.csv", extraction_method="csv", category="Uncategorized",
    )
    db.insert_transactions(db_path, file_id, [tx])
    db.set_transaction_category(
        db_path, tx.id, category="Shopping", subcategory=None, confidence=1.0,
        is_transfer=False, category_source="manual",
    )

    # Re-ingest the same row (e.g. a re-run of ingest over the same file).
    db.insert_transactions(db_path, file_id, [tx])

    fetched = db.get_transaction(db_path, tx.id)
    assert fetched is not None
    assert fetched.category == "Shopping"
    assert fetched.category_source == "manual"
