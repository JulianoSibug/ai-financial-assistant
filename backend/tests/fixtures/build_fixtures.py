"""Synthetic statement builders, used only at test time.

Never write these to disk as committed files -- *.pdf and *.csv are
gitignored (statements must never enter git), so a committed fixture would
be silently untracked and missing on a fresh clone. Tests call these
functions against pytest's tmp_path instead.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


@dataclass
class FixtureTransaction:
    date: date
    description: str
    amount: Decimal


def make_csv_statement(
    path: Path,
    transactions: list[FixtureTransaction],
    *,
    opening_balance: Decimal | None = None,
) -> None:
    lines = ["Date,Description,Amount,Balance"]
    balance = opening_balance
    for tx in transactions:
        if balance is not None:
            balance += tx.amount
            balance_str = f"{balance:.2f}"
        else:
            balance_str = ""
        lines.append(f"{tx.date.strftime('%m/%d/%Y')},{tx.description},{tx.amount:.2f},{balance_str}")
    path.write_text("\n".join(lines) + "\n")


def make_pdf_statement(
    path: Path,
    transactions: list[FixtureTransaction],
    *,
    opening_balance: Decimal,
    closing_balance: Decimal | None = None,
) -> None:
    """Plain-text layout (no ruled table) -- most real bank statement PDFs
    aren't ruled tables either, so this exercises the regex line parser the
    way a real statement would."""
    if closing_balance is None:
        closing_balance = opening_balance + sum((t.amount for t in transactions), Decimal("0"))

    c = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    y = height - 72

    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, y, "Statement of Account")
    y -= 24
    c.setFont("Helvetica", 10)
    c.drawString(72, y, f"Beginning balance: ${opening_balance:.2f}")
    y -= 30

    c.setFont("Helvetica", 9)
    for tx in transactions:
        line = f"{tx.date.strftime('%m/%d/%Y')}  {tx.description}  {tx.amount:.2f}"
        c.drawString(72, y, line)
        y -= 14
        if y < 72:
            c.showPage()
            c.setFont("Helvetica", 9)
            y = height - 72

    y -= 16
    c.setFont("Helvetica", 10)
    c.drawString(72, y, f"Ending balance: ${closing_balance:.2f}")
    c.save()
