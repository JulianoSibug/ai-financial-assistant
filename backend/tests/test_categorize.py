from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from backend import db
from backend.llm.categorize import BatchFailed, categorize_all, parse_categorization_response
from backend.models import Transaction


class FakeProvider:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    def complete(self, prompt: str, max_tokens: int = 4096) -> str:
        self.calls += 1
        return self.response


def _make_tx(merchant: str, *, desc: str, date: str = "2026-08-01", amount: Decimal = Decimal("-10.00")) -> Transaction:
    return Transaction(
        id=db.make_transaction_id("checking", date, desc, amount),
        date=date, description=desc, merchant=merchant, merchant_normalized=merchant.lower(),
        amount=amount, account="checking", source_file="test.csv", extraction_method="csv",
    )


def test_parse_categorization_response_malformed_json_raises() -> None:
    with pytest.raises(BatchFailed):
        parse_categorization_response("not valid json{{{")


def test_parse_categorization_response_non_array_raises() -> None:
    with pytest.raises(BatchFailed):
        parse_categorization_response('{"id": "a"}')


def test_parse_categorization_response_rejects_unknown_category() -> None:
    raw = (
        '[{"id": "a", "category": "Groceries", "confidence": 0.9, "is_transfer": false},'
        ' {"id": "b", "category": "Not A Real Category", "confidence": 0.5, "is_transfer": false}]'
    )
    results = parse_categorization_response(raw)
    assert len(results) == 1
    assert results[0].id == "a"
    assert results[0].category == "Groceries"


def test_categorize_all_missing_transaction_stays_uncategorized(db_path: Path) -> None:
    file_id = db.insert_file(
        db_path, path="/tmp/x.csv", filename="x.csv", size_bytes=1, mtime=0.0,
        sha256="hash-x", file_type="csv",
    )
    tx_starbucks = _make_tx("Starbucks", desc="STARBUCKS #1")
    tx_unknown = _make_tx("Some Weird Merchant", desc="WEIRD MERCHANT XYZ")
    db.insert_transactions(db_path, file_id, [tx_starbucks, tx_unknown])

    # Response only covers tx_starbucks -- tx_unknown is "missing" from it.
    raw = (
        f'[{{"id": "{tx_starbucks.id}", "category": "Dining & Takeout", '
        f'"confidence": 0.95, "is_transfer": false}}]'
    )
    categorize_all(db_path, [tx_starbucks, tx_unknown], FakeProvider(raw))

    fetched_starbucks = db.get_transaction(db_path, tx_starbucks.id)
    fetched_unknown = db.get_transaction(db_path, tx_unknown.id)
    assert fetched_starbucks.category == "Dining & Takeout"
    assert fetched_starbucks.category_source == "llm"
    # The omitted transaction stays Uncategorized -- it must not be dropped.
    assert fetched_unknown is not None
    assert fetched_unknown.category_source == "uncategorized"
    assert fetched_unknown.category is None


def test_categorize_all_uses_cache_on_second_run_without_calling_llm(db_path: Path) -> None:
    file_id = db.insert_file(
        db_path, path="/tmp/y.csv", filename="y.csv", size_bytes=1, mtime=0.0,
        sha256="hash-y", file_type="csv",
    )
    tx = _make_tx("Starbucks", desc="STARBUCKS #1")
    db.insert_transactions(db_path, file_id, [tx])

    raw = f'[{{"id": "{tx.id}", "category": "Dining & Takeout", "confidence": 0.9, "is_transfer": false}}]'
    provider = FakeProvider(raw)
    categorize_all(db_path, [tx], provider)
    assert provider.calls == 1

    tx2 = _make_tx("Starbucks", desc="STARBUCKS #2", date="2026-08-02", amount=Decimal("-6.00"))
    db.insert_transactions(db_path, file_id, [tx2])
    categorize_all(db_path, [tx2], provider)

    assert provider.calls == 1  # unchanged -- cache hit, no new LLM call
    fetched = db.get_transaction(db_path, tx2.id)
    assert fetched.category == "Dining & Takeout"
    assert fetched.category_source == "cache"


def test_categorize_all_dedupes_same_merchant_within_one_run(db_path: Path) -> None:
    file_id = db.insert_file(
        db_path, path="/tmp/z.csv", filename="z.csv", size_bytes=1, mtime=0.0,
        sha256="hash-z", file_type="csv",
    )
    tx1 = _make_tx("Starbucks", desc="STARBUCKS #1")
    tx2 = _make_tx("Starbucks", desc="STARBUCKS #2", date="2026-08-02", amount=Decimal("-6.00"))
    db.insert_transactions(db_path, file_id, [tx1, tx2])

    # Response only names tx1's id -- tx2 shares its merchant and should
    # still get categorized via merchant-level dedup, not left behind.
    raw = f'[{{"id": "{tx1.id}", "category": "Dining & Takeout", "confidence": 0.9, "is_transfer": false}}]'
    provider = FakeProvider(raw)

    categorize_all(db_path, [tx1, tx2], provider)

    assert provider.calls == 1
    assert db.get_transaction(db_path, tx1.id).category == "Dining & Takeout"
    assert db.get_transaction(db_path, tx2.id).category == "Dining & Takeout"


def test_categorize_all_manual_override_survives_recategorization(db_path: Path) -> None:
    file_id = db.insert_file(
        db_path, path="/tmp/w.csv", filename="w.csv", size_bytes=1, mtime=0.0,
        sha256="hash-w", file_type="csv",
    )
    tx = _make_tx("Widget Co", desc="WIDGET CO PAYMENT")
    db.insert_transactions(db_path, file_id, [tx])
    db.set_transaction_category(
        db_path, tx.id, category="Shopping", subcategory=None, confidence=1.0,
        is_transfer=False, category_source="manual",
    )

    # A manual correction should be a cache entry too, so re-running
    # categorize_all for this merchant never calls the LLM at all.
    db.upsert_category_cache(
        db_path, tx.merchant_normalized, category="Shopping", subcategory=None,
        confidence=1.0, is_transfer=False, source="manual", sample_merchant=tx.merchant,
    )
    provider = FakeProvider("[]")
    categorize_all(db_path, [tx], provider)

    assert provider.calls == 0
    fetched = db.get_transaction(db_path, tx.id)
    assert fetched.category == "Shopping"
