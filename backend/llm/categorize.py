"""Stage 4: batched LLM categorization with a merchant-keyed SQLite cache."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from backend import db
from backend.config import CATEGORIES
from backend.ingest.parse_csv import RawTransaction
from backend.llm.provider import LLMProvider
from backend.llm.redact import redact_text
from backend.models import LLMCategorization, LLMExtractedTransaction, Transaction

BATCH_SIZE = 40
MAX_CONCURRENT_CLAUDE = 3

PDF_EXTRACTION_PROMPT_TEMPLATE = """You are extracting transactions from one page of a bank or credit card statement. The text below was extracted from a PDF and may have irregular spacing or run-together columns.

Find every transaction line: a date, a description, and a dollar amount.
Amounts are negative for money out (purchases, payments, fees) and positive
for money in (deposits, refunds, credits) -- use whatever sign the
statement's own layout implies (e.g. a "Payments/Credits" column means
positive even if not printed with a + sign).

Return ONLY a JSON array, no prose, no markdown fences:
[{{"date": "YYYY-MM-DD", "description": "...", "amount": "-12.34"}}]

If a line isn't clearly a transaction, leave it out rather than guessing.

Statement page text:
{page_text}
"""

CATEGORIZE_PROMPT_TEMPLATE = """You are classifying bank transactions into a fixed taxonomy.

Rules:
- Choose exactly one category per transaction from the allowed list. Never invent a category.
- If a merchant is genuinely ambiguous, use "Uncategorized" with low confidence. Do not guess to appear helpful.
- Set is_transfer true for movements between the person's own accounts: credit card payments, "TRANSFER TO SAVINGS", Zelle/Venmo to self, ACH between own banks. These are not spending.
- Set is_transfer true for paycheck deposits only if they are clearly internal transfers; otherwise category "Income".
- Confidence is 0.0-1.0 reflecting how certain the merchant identification is.

Allowed categories: {categories}

Transactions:
{transactions_json}

Return ONLY a JSON array, no prose, no markdown fences:
[{{"id": "...", "category": "...", "subcategory": "...", "confidence": 0.0, "is_transfer": false}}]
"""


class BatchFailed(Exception):
    """Raised when a batch's LLM call or response can't be salvaged. Caught
    by categorize_all so one bad batch doesn't kill the whole run -- its
    transactions simply stay Uncategorized."""


def _build_prompt(batch: list[Transaction]) -> str:
    payload = [
        {"id": tx.id, "merchant": tx.merchant, "amount": str(tx.amount), "date": tx.date.isoformat()}
        for tx in batch
    ]
    return CATEGORIZE_PROMPT_TEMPLATE.format(
        categories=", ".join(CATEGORIES),
        transactions_json=json.dumps(payload),
    )


def parse_categorization_response(raw: str) -> list[LLMCategorization]:
    """Validates the model's JSON array. An element with an unknown category
    or malformed shape is dropped individually (not the whole batch) -- that
    transaction just stays Uncategorized, per spec. A response that isn't
    even a JSON array at all fails the whole batch."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise BatchFailed(f"malformed JSON from categorization response: {e}") from e

    if not isinstance(data, list):
        raise BatchFailed(f"expected a JSON array, got {type(data).__name__}")

    results: list[LLMCategorization] = []
    for item in data:
        try:
            results.append(LLMCategorization.model_validate(item))
        except ValidationError:
            continue
    return results


def categorize_batch(batch: list[Transaction], provider: LLMProvider) -> dict[str, LLMCategorization]:
    prompt = _build_prompt(batch)
    try:
        raw = provider.complete(prompt)
        parsed = parse_categorization_response(raw)
    except BatchFailed:
        raise
    except Exception as e:  # provider transport errors, timeouts, etc.
        raise BatchFailed(str(e)) from e
    return {item.id: item for item in parsed}


def categorize_all(
    db_path: Path,
    transactions: list[Transaction],
    provider: LLMProvider,
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> None:
    """Categorizes every given transaction. Checks the merchant cache first
    (so a second run over the same month makes near-zero LLM calls), then
    deduplicates the remaining cache misses by merchant *within this run
    too* -- if "Starbucks" appears 15 times, the LLM is asked about it once,
    not 15 times, which matters for Claude Pro quota on a large first-time
    ingest.
    """
    uncached: list[Transaction] = []
    for tx in transactions:
        cached = db.get_category_cache(db_path, tx.merchant_normalized)
        if cached is not None:
            db.set_transaction_category(
                db_path, tx.id, category=cached["category"], subcategory=cached["subcategory"],
                confidence=cached["confidence"], is_transfer=bool(cached["is_transfer"]),
                category_source="cache",
            )
        else:
            uncached.append(tx)

    if not uncached:
        if on_progress:
            on_progress(0, 0)
        return

    representatives: dict[str, Transaction] = {}
    members: dict[str, list[Transaction]] = {}
    for tx in uncached:
        members.setdefault(tx.merchant_normalized, []).append(tx)
        representatives.setdefault(tx.merchant_normalized, tx)

    to_call = list(representatives.values())
    batches = [to_call[i : i + BATCH_SIZE] for i in range(0, len(to_call), BATCH_SIZE)]
    completed = 0

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_CLAUDE) as pool:
        futures = {pool.submit(categorize_batch, batch, provider): batch for batch in batches}
        for future in as_completed(futures):
            batch = futures[future]
            completed += 1
            try:
                results = future.result()
            except BatchFailed:
                results = {}

            for representative_tx in batch:
                item = results.get(representative_tx.id)
                if item is None:
                    continue  # omitted by the model -> stays Uncategorized, never dropped
                merchant_key = representative_tx.merchant_normalized
                db.upsert_category_cache(
                    db_path, merchant_key, category=item.category, subcategory=item.subcategory,
                    confidence=item.confidence, is_transfer=item.is_transfer, source="llm",
                    sample_merchant=representative_tx.merchant,
                )
                for member_tx in members[merchant_key]:
                    db.set_transaction_category(
                        db_path, member_tx.id, category=item.category, subcategory=item.subcategory,
                        confidence=item.confidence, is_transfer=item.is_transfer, category_source="llm",
                    )

            if on_progress:
                on_progress(completed, len(batches))


def extract_pdf_transactions(page_text: str, provider: LLMProvider) -> list[RawTransaction]:
    """The PDF LLM-extraction fallback (parse_pdf.py's llm_fallback param):
    used only for pages where the regex line parser under-recovers. Redacts
    before sending, same as every other LLM call in this app."""
    prompt = PDF_EXTRACTION_PROMPT_TEMPLATE.format(page_text=redact_text(page_text))
    try:
        raw = provider.complete(prompt)
        data = json.loads(raw)
    except Exception:
        return []

    if not isinstance(data, list):
        return []

    results: list[RawTransaction] = []
    for item in data:
        try:
            parsed = LLMExtractedTransaction.model_validate(item)
        except ValidationError:
            continue
        results.append(RawTransaction(date=parsed.date, description=parsed.description, amount=parsed.amount))
    return results
