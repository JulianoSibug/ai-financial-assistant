"""Stage 2 (tabular): CSV / OFX / QFX -> ParsedStatement. Fully deterministic."""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

# --- shared money / date parsing (also used by parse_pdf.py and reconcile.py) ---


def parse_money(text: str | None) -> Decimal | None:
    """Parse a money string into a signed Decimal.

    Handles '$1,234.56', '-$1,234.56', '(1,234.56)' (parenthesized negative,
    the common statement convention), and '1234.56-' (trailing minus)."""
    if text is None:
        return None
    t = text.strip()
    if not t:
        return None

    negative = False
    if t.startswith("(") and t.endswith(")"):
        negative = True
        t = t[1:-1].strip()
    if t.endswith("-"):
        negative = True
        t = t[:-1].strip()
    if t.startswith("-"):
        negative = True
        t = t[1:].strip()
    elif t.startswith("+"):
        t = t[1:].strip()

    t = t.replace("$", "").replace(",", "").strip()
    if not re.match(r"^\d+(\.\d+)?$", t):
        return None
    try:
        value = Decimal(t)
    except InvalidOperation:
        return None
    return -value if negative else value


DATE_FORMATS = [
    "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%d/%m/%Y",
    "%B %d, %Y", "%b %d, %Y", "%b %d %Y", "%Y%m%d",
]


def parse_date_str(text: str | None) -> date | None:
    if not text:
        return None
    t = text.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


@dataclass
class RawTransaction:
    date: date
    description: str
    amount: Decimal
    balance: Decimal | None = None


@dataclass
class ParsedStatement:
    transactions: list[RawTransaction] = field(default_factory=list)
    account_hint: str | None = None
    opening_balance: Decimal | None = None
    closing_balance: Decimal | None = None
    total_debits: Decimal | None = None
    total_credits: Decimal | None = None


# --- CSV header scoring ---

HEADER_SYNONYMS: dict[str, list[str]] = {
    "date": ["transaction date", "posting date", "trans date", "date"],
    "description": ["description", "payee", "memo", "transaction description", "name"],
    "amount": ["amount", "transaction amount", "amt"],
    "debit": ["debit", "withdrawal", "withdrawals", "payment", "debit amount"],
    "credit": ["credit", "deposit", "deposits", "credit amount"],
    "balance": ["balance", "running balance", "ending balance"],
}


def score_headers(headers: list[str]) -> dict[str, int]:
    """Map each role (date/description/amount/debit/credit/balance) to the
    index of its best-matching header column, via synonym scoring."""
    normalized = [h.strip().lower() for h in headers]
    mapping: dict[str, int] = {}
    for role, synonyms in HEADER_SYNONYMS.items():
        best_idx: int | None = None
        best_score = -1
        for idx, h in enumerate(normalized):
            score = -1
            if h in synonyms:
                score = 100 - synonyms.index(h)
            else:
                for rank, syn in enumerate(synonyms):
                    if syn in h:
                        score = 50 - rank
                        break
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_idx is not None and best_score >= 0:
            mapping[role] = best_idx

    # A dedicated debit/credit pair takes precedence over a coincidental
    # "amount" substring match landing on one of those same columns.
    if "debit" in mapping and "credit" in mapping and mapping.get("amount") in (
        mapping["debit"], mapping["credit"],
    ):
        mapping.pop("amount", None)
    return mapping


def _sniff_dialect(sample: str) -> type[csv.Dialect]:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.get_dialect("excel")


def parse_csv_file(path: Path) -> ParsedStatement:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return ParsedStatement()

    dialect = _sniff_dialect("\n".join(lines[:10]))
    rows = list(csv.reader(lines, dialect=dialect))
    if not rows:
        return ParsedStatement()

    header, data_rows = rows[0], rows[1:]
    mapping = score_headers(header)
    has_debit_credit = "debit" in mapping and "credit" in mapping

    result = ParsedStatement()
    for row in data_rows:
        if not row or len(row) <= max(mapping.values(), default=-1):
            continue

        tx_date = parse_date_str(row[mapping["date"]]) if "date" in mapping else None
        if tx_date is None:
            continue
        description = row[mapping["description"]].strip() if "description" in mapping else ""

        amount: Decimal | None = None
        if has_debit_credit:
            debit = parse_money(row[mapping["debit"]])
            credit = parse_money(row[mapping["credit"]])
            if debit not in (None, Decimal(0)):
                amount = -abs(debit)
            elif credit not in (None, Decimal(0)):
                amount = abs(credit)
            else:
                amount = Decimal("0")
        elif "amount" in mapping:
            amount = parse_money(row[mapping["amount"]])

        if amount is None:
            continue

        balance = parse_money(row[mapping["balance"]]) if "balance" in mapping else None
        result.transactions.append(RawTransaction(date=tx_date, description=description, amount=amount, balance=balance))

    if result.transactions:
        first, last = result.transactions[0], result.transactions[-1]
        if last.balance is not None:
            result.closing_balance = last.balance
        if first.balance is not None:
            result.opening_balance = first.balance - first.amount

    return result


# --- OFX / QFX (regex tag extraction; OFX is often SGML, not well-formed XML) ---

_OFX_TAG_RE = re.compile(r"<(\w+)>([^<\r\n]*)")
_STMTTRN_RE = re.compile(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|$)", re.DOTALL | re.IGNORECASE)


def _ofx_tags(block: str) -> dict[str, str]:
    return {m.group(1).upper(): m.group(2).strip() for m in _OFX_TAG_RE.finditer(block)}


def parse_ofx_file(path: Path) -> ParsedStatement:
    text = path.read_text(encoding="utf-8", errors="replace")
    result = ParsedStatement()

    for match in _STMTTRN_RE.finditer(text):
        tags = _ofx_tags(match.group(1))
        tx_date = parse_date_str(tags.get("DTPOSTED", "")[:8]) if tags.get("DTPOSTED") else None
        amount = parse_money(tags.get("TRNAMT"))
        description = tags.get("NAME") or tags.get("MEMO") or ""
        if tx_date is None or amount is None:
            continue
        result.transactions.append(RawTransaction(date=tx_date, description=description, amount=amount))

    ledger_match = re.search(r"<LEDGERBAL>(.*?)</LEDGERBAL>", text, re.DOTALL | re.IGNORECASE)
    if ledger_match:
        result.closing_balance = parse_money(_ofx_tags(ledger_match.group(1)).get("BALAMT"))

    acct_match = re.search(r"<ACCTID>([^<\r\n]*)", text, re.IGNORECASE)
    if acct_match:
        result.account_hint = acct_match.group(1).strip()

    return result


def parse_tabular_file(path: Path, file_type: str) -> ParsedStatement:
    if file_type == "csv":
        return parse_csv_file(path)
    if file_type in ("ofx", "qfx"):
        return parse_ofx_file(path)
    raise ValueError(f"parse_tabular_file cannot handle file_type={file_type!r}")
