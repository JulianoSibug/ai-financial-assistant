"""Stage 5: verify parsed transactions against the statement's own claimed
balance figures. This is the single most important correctness feature in
the app -- a real mismatch must surface as a visible warning, never pass
silently. Best-effort by nature: statement layouts vary too much to
guarantee every one exposes a checkable balance line.
"""
from __future__ import annotations

from pathlib import Path

from backend import db

TOLERANCE_CENTS = 1  # $0.01


def reconcile_file(db_path: Path, file_id: int) -> str:
    """Computes and persists the reconciliation result for one file. Returns
    the resulting status ('ok' | 'warning' | 'not_applicable')."""
    file_row = db.get_file(db_path, file_id)
    if file_row is None:
        raise ValueError(f"no such file_id: {file_id}")

    transactions = db.get_transactions_for_file(db_path, file_id)
    computed_sum_cents = sum(db.to_cents(tx.amount) for tx in transactions)

    opening = file_row["statement_opening_cents"]
    closing = file_row["statement_closing_cents"]
    total_debits = file_row["statement_total_debits_cents"]
    total_credits = file_row["statement_total_credits_cents"]

    if opening is not None and closing is not None:
        status, delta_cents, detail = _check_opening_closing(opening, closing, computed_sum_cents)
    elif total_debits is not None or total_credits is not None:
        status, delta_cents, detail = _check_totals(total_debits, total_credits, transactions)
    else:
        status, delta_cents, detail = (
            "not_applicable",
            0,
            "No balance or total figures were found in this statement to check against.",
        )

    db.upsert_reconciliation(
        db_path,
        file_id,
        statement_opening_cents=opening,
        statement_closing_cents=closing,
        statement_total_debits_cents=total_debits,
        statement_total_credits_cents=total_credits,
        computed_sum_cents=computed_sum_cents,
        delta_cents=delta_cents,
        status=status,
        detail=detail,
    )
    return status


def _check_opening_closing(opening: int, closing: int, computed_sum_cents: int) -> tuple[str, int, str | None]:
    expected_closing = opening + computed_sum_cents
    delta_cents = closing - expected_closing
    if abs(delta_cents) > TOLERANCE_CENTS:
        detail = (
            f"Statement closing balance is {db.from_cents(closing)}, but opening balance "
            f"({db.from_cents(opening)}) plus parsed transactions ({db.from_cents(computed_sum_cents)}) "
            f"gives {db.from_cents(expected_closing)} -- a difference of {db.from_cents(delta_cents)}."
        )
        return "warning", delta_cents, detail
    return "ok", delta_cents, None


def _check_totals(
    total_debits: int | None, total_credits: int | None, transactions: list
) -> tuple[str, int, str | None]:
    computed_debits = -sum(db.to_cents(tx.amount) for tx in transactions if tx.amount < 0)
    computed_credits = sum(db.to_cents(tx.amount) for tx in transactions if tx.amount > 0)

    worst_delta = 0
    problems: list[str] = []
    if total_debits is not None:
        d = computed_debits - total_debits
        if abs(d) > abs(worst_delta):
            worst_delta = d
        if abs(d) > TOLERANCE_CENTS:
            problems.append(
                f"parsed debits {db.from_cents(computed_debits)} vs. statement total {db.from_cents(total_debits)}"
            )
    if total_credits is not None:
        d = computed_credits - total_credits
        if abs(d) > abs(worst_delta):
            worst_delta = d
        if abs(d) > TOLERANCE_CENTS:
            problems.append(
                f"parsed credits {db.from_cents(computed_credits)} vs. statement total {db.from_cents(total_credits)}"
            )

    if problems:
        return "warning", worst_delta, "; ".join(problems)
    return "ok", worst_delta, None
