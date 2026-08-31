"""Stage 5 support + narrative generation.

Every number here is computed in Python from parsed data -- recurring-charge
detection is a deterministic pass, and the narrative prompt hands the model
a finished stats block it can only write prose around, never compute from.
"""
from __future__ import annotations

import calendar
import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from backend import db
from backend.llm.provider import LLMProvider
from backend.models import (
    CategoryTotal,
    DailyPoint,
    MerchantTotal,
    ReconciliationWarning,
    RecurringCharge,
    Transaction,
)

NARRATIVE_PROMPT_TEMPLATE = """You are writing a monthly spending summary for the person whose money this is.
Write in second person, plain language, no financial-advisor throat-clearing.

Here are the computed figures. Every number you cite must come from this block verbatim.
Do not calculate anything. Do not estimate. Do not add numbers together.

{stats_json}

Write:
1. A two-sentence overview of the month.
2. Three to five observations, each one sentence, that a person could act on. Prioritize
   things that are surprising, not things that are obvious. "You spent money on groceries"
   is not an observation. "Dining is 34% above your grocery spend" is.
3. A short "worth a look" list: recurring charges, duplicate charges, unusually large
   one-offs, or categories that moved sharply.

Do not moralize, do not tell me to make a budget, do not use the word "journey".
If the data is too thin to support a claim, say so instead of filling space.
Return markdown. No heading above level 3.
"""


def _period_bounds(period: str) -> tuple[date, date]:
    year, month = (int(p) for p in period.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _prior_period(period: str) -> str:
    year, month = (int(p) for p in period.split("-"))
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


def _date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def detect_recurring_charges(transactions: list[Transaction]) -> list[RecurringCharge]:
    """Same normalized merchant + same amount 2+ times, or same merchant
    across 2+ consecutive months (amount may vary)."""
    by_merchant: dict[str, list[Transaction]] = defaultdict(list)
    for t in transactions:
        if t.amount < 0 and not t.is_transfer:
            by_merchant[t.merchant_normalized].append(t)

    results: list[RecurringCharge] = []
    for txs in by_merchant.values():
        if len(txs) < 2:
            continue
        txs_sorted = sorted(txs, key=lambda t: t.date)
        display_name = txs_sorted[-1].merchant

        amount_counts: dict[Decimal, int] = defaultdict(int)
        for t in txs_sorted:
            amount_counts[t.amount] += 1
        best_amount, best_count = max(amount_counts.items(), key=lambda kv: kv[1])

        if best_count >= 2:
            same_amount_dates = [t.date for t in txs_sorted if t.amount == best_amount]
            results.append(
                RecurringCharge(
                    merchant=display_name, amount=-best_amount,
                    cadence=_infer_cadence(same_amount_dates), occurrences=best_count,
                )
            )
            continue

        months = sorted({(t.date.year, t.date.month) for t in txs_sorted})
        if len(months) >= 2 and _are_consecutive_months(months):
            results.append(
                RecurringCharge(
                    merchant=display_name, amount=None,
                    cadence=_infer_cadence([t.date for t in txs_sorted]), occurrences=len(txs_sorted),
                )
            )

    return results


def _are_consecutive_months(months: list[tuple[int, int]]) -> bool:
    for (y1, m1), (y2, m2) in zip(months, months[1:]):
        expected = (y1, m1 + 1) if m1 < 12 else (y1 + 1, 1)
        if (y2, m2) != expected:
            return False
    return True


def _infer_cadence(dates: list[date]) -> str:
    dates = sorted(dates)
    if len(dates) < 2:
        return "unknown"
    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    avg_gap = sum(gaps) / len(gaps)
    if avg_gap <= 10:
        return "weekly"
    if avg_gap <= 20:
        return "biweekly"
    if avg_gap <= 45:
        return "monthly"
    if avg_gap <= 100:
        return "quarterly"
    return "irregular"


def compute_summary_stats(db_path: Path, period: str) -> dict:
    start, end = _period_bounds(period)
    all_tx = db.get_all_transactions(db_path)
    period_tx = [t for t in all_tx if start <= t.date <= end]
    spend_tx = [t for t in period_tx if not t.is_transfer]

    total_out = -sum((t.amount for t in spend_tx if t.amount < 0), Decimal("0"))
    total_in = sum((t.amount for t in spend_tx if t.amount > 0), Decimal("0"))

    category_sums: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for t in spend_tx:
        if t.amount < 0:
            category_sums[t.category or "Uncategorized"] += -t.amount
    total_spend = sum(category_sums.values(), Decimal("0")) or Decimal("1")

    prior_start, prior_end = _period_bounds(_prior_period(period))
    prior_tx = [t for t in all_tx if prior_start <= t.date <= prior_end and not t.is_transfer]
    have_prior_data = len(prior_tx) > 0
    prior_category_sums: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for t in prior_tx:
        if t.amount < 0:
            prior_category_sums[t.category or "Uncategorized"] += -t.amount

    category_totals = [
        CategoryTotal(
            category=cat,
            total=amt,
            percent=float(amt / total_spend * 100),
            delta_vs_prior=(amt - prior_category_sums[cat]) if have_prior_data else None,
        )
        for cat, amt in sorted(category_sums.items(), key=lambda kv: kv[1], reverse=True)
    ]

    merchant_amounts: dict[str, list[Decimal]] = defaultdict(list)
    for t in spend_tx:
        if t.amount < 0:
            merchant_amounts[t.merchant].append(t.amount)
    top_merchants = sorted(
        (
            MerchantTotal(merchant=m, count=len(amounts), total=-sum(amounts, Decimal("0")))
            for m, amounts in merchant_amounts.items()
        ),
        key=lambda mt: mt.total,
        reverse=True,
    )[:10]

    daily_sums: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
    for t in spend_tx:
        if t.amount < 0:
            daily_sums[t.date] += -t.amount
    daily_series = [DailyPoint(date=d, total_out=daily_sums.get(d, Decimal("0"))) for d in _date_range(start, end)]

    largest_transactions = sorted((t for t in spend_tx if t.amount < 0), key=lambda t: t.amount)[:5]

    reconciliation_warnings = [
        ReconciliationWarning(
            file_id=r["file_id"], filename=r["filename"], status=r["status"],
            delta=db.from_cents(r["delta_cents"]), detail=r["detail"],
        )
        for r in db.get_reconciliation_warnings(db_path)
    ]

    return {
        "period": period,
        "total_in": total_in,
        "total_out": total_out,
        "net": total_in - total_out,
        "transaction_count": len(spend_tx),
        "days_covered": (end - start).days + 1,
        "category_totals": category_totals,
        "top_merchants": top_merchants,
        "largest_transactions": largest_transactions,
        "daily_series": daily_series,
        "recurring_charges": detect_recurring_charges(all_tx),
        "reconciliation_warnings": reconciliation_warnings,
    }


def _stats_to_json_safe(stats: dict) -> dict:
    result: dict = {}
    for key, value in stats.items():
        if isinstance(value, list) and value and hasattr(value[0], "model_dump"):
            result[key] = [item.model_dump(mode="json") for item in value]
        elif isinstance(value, Decimal):
            result[key] = str(value)
        else:
            result[key] = value
    return result


def generate_narrative(stats: dict, provider: LLMProvider) -> str:
    prompt = NARRATIVE_PROMPT_TEMPLATE.format(stats_json=json.dumps(_stats_to_json_safe(stats), indent=2))
    return provider.complete(prompt, max_tokens=2048)
