from __future__ import annotations

import json

from backend.llm.manual_provider import ManualCategorizationProvider
from backend.llm.categorize import CATEGORIZE_PROMPT_TEMPLATE
from backend.config import CATEGORIES


def _categorize_prompt(transactions: list[dict]) -> str:
    return CATEGORIZE_PROMPT_TEMPLATE.format(
        categories=", ".join(CATEGORIES), transactions_json=json.dumps(transactions)
    )


def test_known_merchant_returns_expected_category() -> None:
    prompt = _categorize_prompt([{"id": "a", "merchant": "Netflix.Com Netflix.Com", "amount": "-8.99", "date": "2026-08-01"}])
    result = json.loads(ManualCategorizationProvider().complete(prompt))
    assert result == [{"id": "a", "category": "Subscriptions", "subcategory": "Netflix", "confidence": 0.95, "is_transfer": False}]


def test_lookup_is_case_insensitive() -> None:
    prompt = _categorize_prompt([{"id": "a", "merchant": "NETFLIX.COM NETFLIX.COM", "amount": "-8.99", "date": "2026-08-01"}])
    result = json.loads(ManualCategorizationProvider().complete(prompt))
    assert result[0]["category"] == "Subscriptions"


def test_unknown_merchant_falls_back_to_uncategorized() -> None:
    prompt = _categorize_prompt([{"id": "a", "merchant": "Some Totally New Merchant Xyz", "amount": "-8.99", "date": "2026-08-01"}])
    result = json.loads(ManualCategorizationProvider().complete(prompt))
    assert result[0]["category"] == "Uncategorized"
    assert result[0]["confidence"] < 0.5


def test_every_mapped_category_is_in_the_fixed_taxonomy() -> None:
    from backend.llm.manual_provider import MERCHANT_CATEGORIES

    for merchant, (category, _sub, confidence, _transfer) in MERCHANT_CATEGORIES.items():
        assert category in CATEGORIES, f"{merchant!r} maps to invalid category {category!r}"
        assert 0.0 <= confidence <= 1.0


def test_narrative_prompt_returns_placeholder_not_garbage() -> None:
    narrative_prompt = "Write a two-sentence overview of the month.\n\n{}"
    result = ManualCategorizationProvider().complete(narrative_prompt)
    assert "real LLM connection" in result
    with_no_json_crash = True
    try:
        json.loads(result)
        with_no_json_crash = False  # it shouldn't look like valid categorization JSON
    except json.JSONDecodeError:
        pass
    assert with_no_json_crash


def test_multiple_transactions_in_one_batch() -> None:
    prompt = _categorize_prompt([
        {"id": "a", "merchant": "Starbucks", "amount": "-4.75", "date": "2026-08-01"},
        {"id": "b", "merchant": "Aldi", "amount": "-30.00", "date": "2026-08-02"},
    ])
    result = json.loads(ManualCategorizationProvider().complete(prompt))
    assert len(result) == 2
    by_id = {r["id"]: r for r in result}
    assert by_id["b"]["category"] == "Groceries"
    # "Starbucks" isn't in the manual mapping (not part of the real dataset) -> uncategorized
    assert by_id["a"]["category"] == "Uncategorized"
