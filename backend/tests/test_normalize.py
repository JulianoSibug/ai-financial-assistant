from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.ingest.normalize import build_transactions, clean_merchant, derive_account_from_filename, normalize_merchant_key
from backend.ingest.parse_csv import RawTransaction


def test_strips_store_number() -> None:
    assert clean_merchant("STARBUCKS #4471") == "Starbucks"


def test_strips_square_processor_prefix() -> None:
    assert clean_merchant("SQ *BLUE BOTTLE COFFEE") == "Blue Bottle Coffee"


def test_strips_toast_processor_prefix_no_space() -> None:
    assert clean_merchant("TST*THE CORNER BISTRO") == "The Corner Bistro"


def test_strips_city_state_suffix() -> None:
    assert clean_merchant("WALGREENS SEATTLE WA") == "Walgreens"
    assert clean_merchant("SHELL OIL AUSTIN TX") == "Shell Oil"


def test_strips_trailing_reference_code() -> None:
    assert clean_merchant("AMAZON MKTPLACE REF4F92A1") == "Amazon Mktplace"


def test_strips_trailing_digits() -> None:
    assert clean_merchant("CHEVRON 00012345") == "Chevron"


def test_combined_store_number_and_city_state() -> None:
    assert clean_merchant("WALMART SUPERCENTER #1234 AUSTIN TX") == "Walmart Supercenter"


def test_strips_trailing_mcc_category_label_then_city_state() -> None:
    """Credit-card statements often append a category column after the
    merchant, which would otherwise push city/state out of trailing
    position and block that cleanup too."""
    assert clean_merchant("WALMART STORE 02015 FAIRFAX VA Merchandise") == "Walmart Store"
    assert clean_merchant("BJS WHOLESALE #0033 FAIRFAX VA Warehouse Clubs") == "Bjs Wholesale"


def test_does_not_mangle_ordinary_merchant_names() -> None:
    assert clean_merchant("Blue Bottle Coffee") == "Blue Bottle Coffee"
    assert clean_merchant("NETFLIX.COM") == "Netflix.Com"


def test_build_transactions_flags_obvious_transfer() -> None:
    raw = RawTransaction(date=date(2026, 8, 10), description="Paid To - Discover E-Payment Chk 9100001", amount=Decimal("-1412.37"))
    txs = build_transactions([raw], account="checking", source_file="s.pdf", extraction_method="regex")
    assert txs[0].is_transfer is True
    assert txs[0].category == "Transfers"
    assert txs[0].category_source == "rule"


def test_build_transactions_does_not_flag_ordinary_purchase() -> None:
    raw = RawTransaction(date=date(2026, 8, 10), description="WHOLE FOODS MARKET", amount=Decimal("-42.00"))
    txs = build_transactions([raw], account="checking", source_file="s.pdf", extraction_method="regex")
    assert txs[0].is_transfer is False
    assert txs[0].category_source == "uncategorized"


def test_normalize_merchant_key_collapses_variants() -> None:
    a = normalize_merchant_key(clean_merchant("STARBUCKS #4471"))
    b = normalize_merchant_key(clean_merchant("STARBUCKS #0092"))
    assert a == b == "starbucks"


def test_derive_account_from_filename() -> None:
    assert derive_account_from_filename("chase_checking_aug2026.csv") == "Chase Checking Aug2026"
    assert derive_account_from_filename("Amex-Gold.pdf") == "Amex Gold"
