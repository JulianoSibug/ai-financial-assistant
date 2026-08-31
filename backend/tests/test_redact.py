from __future__ import annotations

from backend.llm.redact import redact_text


def test_ssn_hyphenated() -> None:
    assert redact_text("SSN: 123-45-6789 on file") == "SSN: [REDACTED] on file"


def test_ssn_space_separated() -> None:
    assert redact_text("SSN 123 45 6789") == "SSN [REDACTED]"


def test_ssn_bare_digits_caught_by_generic_run() -> None:
    assert "123456789" not in redact_text("SSN 123456789")


def test_card_number_hyphen_grouped() -> None:
    assert redact_text("card 4111-1111-1111-1111 charged") == "card [REDACTED] charged"


def test_card_number_space_grouped() -> None:
    assert redact_text("card 4111 1111 1111 1111 charged") == "card [REDACTED] charged"


def test_card_number_bare_digits() -> None:
    assert "4111111111111111" not in redact_text("card 4111111111111111 charged")


def test_account_number_labeled() -> None:
    result = redact_text("Account #1234567890 balance")
    assert "1234567890" not in result
    assert "[REDACTED]" in result


def test_account_number_with_ending_in_phrasing() -> None:
    result = redact_text("account ending in 43219876")
    assert "43219876" not in result


def test_full_address() -> None:
    result = redact_text("Mail to 123 Main St, Anytown, CA 90210 please")
    assert "123 Main St" not in result
    assert "90210" not in result
    assert "Mail to" in result
    assert "please" in result


# --- negative tests: these must survive untouched ---

def test_dollar_amount_survives() -> None:
    assert redact_text("Total: $1,234.56") == "Total: $1,234.56"


def test_large_dollar_amount_survives() -> None:
    assert redact_text("Total: $12,345,678.90") == "Total: $12,345,678.90"


def test_date_survives() -> None:
    assert redact_text("Transaction on 08/15/2026") == "Transaction on 08/15/2026"


def test_iso_date_survives() -> None:
    assert redact_text("Transaction on 2026-08-15") == "Transaction on 2026-08-15"


def test_merchant_with_store_number_survives() -> None:
    assert redact_text("STARBUCKS #4471 SEATTLE WA") == "STARBUCKS #4471 SEATTLE WA"


def test_plain_merchant_name_survives() -> None:
    assert redact_text("WHOLE FOODS MARKET") == "WHOLE FOODS MARKET"
