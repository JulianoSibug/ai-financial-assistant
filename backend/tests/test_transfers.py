from __future__ import annotations

from backend.ingest.transfers import looks_like_transfer


def test_transfer_to_checking() -> None:
    assert looks_like_transfer("Transfer To Checking")


def test_transfer_from_shares() -> None:
    assert looks_like_transfer("Transfer From Shares")


def test_credit_card_e_payment_detected() -> None:
    assert looks_like_transfer("Paid To - Discover E-Payment Chk 9100001")


def test_credit_card_e_payment_detected_with_ocr_injected_space() -> None:
    """pdfplumber's extraction has been observed splitting 'Payment' into
    'P ayment' inline within this exact phrase on a real statement."""
    assert looks_like_transfer("Paid To - Discover E-P ayment Chk 9100001")


def test_citizens_bank_not_confused_with_citi() -> None:
    assert not looks_like_transfer("Paid To - Citizens Bank E-Payment Chk 1234567")


def test_credit_card_payment_confirmation_on_card_statement() -> None:
    assert looks_like_transfer("INTERNET PAYMENT - THANK YOU")


def test_real_expense_with_paid_to_prefix_not_flagged() -> None:
    """The same bank uses "Paid To -" for real spending too -- it must not
    be treated as a transfer signal on its own."""
    assert not looks_like_transfer("Paid To - Planet Fitness H Iclub Fees Chk 6200001")
    assert not looks_like_transfer("Paid To - Rocket Money Premium Chk 9100001")


def test_ordinary_purchase_not_flagged() -> None:
    assert not looks_like_transfer("WALMART STORE 02015 FAIRFAX VA")
    assert not looks_like_transfer("Whole Foods Market")


def test_zelle_to_another_person_not_flagged() -> None:
    """Zelle to self would be a transfer, but to someone else it's a real
    payment -- the description alone can't tell them apart, so this stays
    unflagged for the LLM (which has more context) to judge."""
    assert not looks_like_transfer("Zelle DB Syed Tirmizi")
