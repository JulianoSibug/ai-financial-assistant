"""SQLite schema and queries. Plain DB-API, no ORM.

Money is stored as INTEGER cents (never REAL/float) so native SQL ordering,
range filters, and SUM() are correct. Decimal <-> cents conversion happens at
the read/write boundary via to_cents/from_cents.
"""
from __future__ import annotations

import contextlib
import datetime
import hashlib
import sqlite3
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Iterator

from backend.models import Transaction

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    filename TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mtime REAL NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    file_type TEXT NOT NULL,
    account TEXT,
    status TEXT NOT NULL DEFAULT 'discovered',
    error_message TEXT,
    discovered_at TEXT NOT NULL,
    extracted_at TEXT,
    transaction_count INTEGER NOT NULL DEFAULT 0,
    -- Balance figures as stated BY the statement itself, captured at
    -- extraction time (stage 2). Reconciliation (stage 5) compares these
    -- against the actual sum of parsed transactions, possibly in a later
    -- API call, so they must be persisted rather than recomputed.
    statement_opening_cents INTEGER,
    statement_closing_cents INTEGER,
    statement_total_debits_cents INTEGER,
    statement_total_credits_cents INTEGER
) STRICT;

CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    description TEXT NOT NULL,
    merchant TEXT NOT NULL,
    merchant_normalized TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    account TEXT NOT NULL,
    source_file TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    category TEXT,
    subcategory TEXT,
    confidence REAL,
    is_transfer INTEGER NOT NULL DEFAULT 0,
    category_source TEXT NOT NULL DEFAULT 'uncategorized',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category);
CREATE INDEX IF NOT EXISTS idx_tx_merchant_norm ON transactions(merchant_normalized);
CREATE INDEX IF NOT EXISTS idx_tx_account ON transactions(account);

CREATE TABLE IF NOT EXISTS category_cache (
    merchant_normalized TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    subcategory TEXT,
    confidence REAL,
    is_transfer INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL,
    sample_merchant TEXT,
    hit_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS reconciliation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL UNIQUE REFERENCES files(id) ON DELETE CASCADE,
    statement_opening_cents INTEGER,
    statement_closing_cents INTEGER,
    statement_total_debits_cents INTEGER,
    statement_total_credits_cents INTEGER,
    computed_sum_cents INTEGER NOT NULL,
    delta_cents INTEGER NOT NULL,
    status TEXT NOT NULL,
    detail TEXT,
    checked_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS period_summary (
    period TEXT PRIMARY KEY,
    narrative_markdown TEXT,
    stats_json TEXT NOT NULL,
    generated_at TEXT NOT NULL
) STRICT;
"""


def to_cents(amount: Decimal) -> int:
    return int((Decimal(amount) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def from_cents(cents: int) -> Decimal:
    return (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"))


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def make_transaction_id(account: str, date: str, description: str, amount: Decimal) -> str:
    raw = f"{account}|{date}|{description}|{amount}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@contextlib.contextmanager
def get_connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path) -> None:
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)


# --- files -------------------------------------------------------------

def get_file_by_hash(db_path: Path, sha256: str) -> dict[str, Any] | None:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM files WHERE sha256 = ?", (sha256,)).fetchone()
        return dict(row) if row else None


def insert_file(
    db_path: Path,
    *,
    path: str,
    filename: str,
    size_bytes: int,
    mtime: float,
    sha256: str,
    file_type: str,
    account: str | None = None,
) -> int:
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO files (path, filename, size_bytes, mtime, sha256, file_type, account,
                                status, discovered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'discovered', ?)
            """,
            (path, filename, size_bytes, mtime, sha256, file_type, account, now_iso()),
        )
        return int(cur.lastrowid)


def update_file_status(
    db_path: Path,
    file_id: int,
    *,
    status: str,
    error_message: str | None = None,
    transaction_count: int | None = None,
    account: str | None = None,
    mark_extracted: bool = False,
) -> None:
    with get_connection(db_path) as conn:
        fields = ["status = ?"]
        params: list[Any] = [status]
        if error_message is not None:
            fields.append("error_message = ?")
            params.append(error_message)
        if transaction_count is not None:
            fields.append("transaction_count = ?")
            params.append(transaction_count)
        if account is not None:
            fields.append("account = ?")
            params.append(account)
        if mark_extracted:
            fields.append("extracted_at = ?")
            params.append(now_iso())
        params.append(file_id)
        conn.execute(f"UPDATE files SET {', '.join(fields)} WHERE id = ?", params)


def set_file_statement_balances(
    db_path: Path,
    file_id: int,
    *,
    opening_cents: int | None,
    closing_cents: int | None,
    total_debits_cents: int | None,
    total_credits_cents: int | None,
) -> None:
    """Persists the balance figures the statement itself claims (captured at
    extraction time) so reconciliation can check against them later, even in
    a separate /api/analyze call."""
    with get_connection(db_path) as conn:
        conn.execute(
            """
            UPDATE files
            SET statement_opening_cents = ?, statement_closing_cents = ?,
                statement_total_debits_cents = ?, statement_total_credits_cents = ?
            WHERE id = ?
            """,
            (opening_cents, closing_cents, total_debits_cents, total_credits_cents, file_id),
        )


def list_files(db_path: Path) -> list[dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT * FROM files ORDER BY discovered_at").fetchall()
        return [dict(r) for r in rows]


def get_file(db_path: Path, file_id: int) -> dict[str, Any] | None:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        return dict(row) if row else None


# --- transactions --------------------------------------------------------

def _row_to_transaction(row: sqlite3.Row) -> Transaction:
    return Transaction(
        id=row["id"],
        date=row["date"],
        description=row["description"],
        merchant=row["merchant"],
        merchant_normalized=row["merchant_normalized"],
        amount=from_cents(row["amount_cents"]),
        account=row["account"],
        source_file=row["source_file"],
        extraction_method=row["extraction_method"],
        category=row["category"],
        subcategory=row["subcategory"],
        confidence=row["confidence"],
        is_transfer=bool(row["is_transfer"]),
        category_source=row["category_source"],
    )


def insert_transactions(db_path: Path, file_id: int, transactions: list[Transaction]) -> int:
    """INSERT OR IGNORE so re-ingesting overlapping statements is a no-op for
    rows that already exist, and never clobbers a manually-corrected row."""
    inserted = 0
    with get_connection(db_path) as conn:
        for tx in transactions:
            ts = now_iso()
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO transactions (
                    id, file_id, date, description, merchant, merchant_normalized,
                    amount_cents, account, source_file, extraction_method,
                    category, subcategory, confidence, is_transfer, category_source,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tx.id, file_id, tx.date.isoformat(), tx.description, tx.merchant,
                    tx.merchant_normalized, to_cents(tx.amount), tx.account, tx.source_file,
                    tx.extraction_method, tx.category, tx.subcategory, tx.confidence,
                    int(tx.is_transfer), tx.category_source, ts, ts,
                ),
            )
            inserted += cur.rowcount
    return inserted


def get_transaction(db_path: Path, tx_id: str) -> Transaction | None:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        return _row_to_transaction(row) if row else None


def get_transactions_for_file(db_path: Path, file_id: int) -> list[Transaction]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE file_id = ? ORDER BY date", (file_id,)
        ).fetchall()
        return [_row_to_transaction(r) for r in rows]


def get_all_transactions(db_path: Path) -> list[Transaction]:
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT * FROM transactions ORDER BY date").fetchall()
        return [_row_to_transaction(r) for r in rows]


def query_transactions(
    db_path: Path,
    *,
    category: str | None = None,
    account: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_amount_cents: int | None = None,
    max_amount_cents: int | None = None,
    merchant_search: str | None = None,
    include_transfers: bool = True,
    sort_by: str = "date",
    sort_dir: str = "desc",
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Transaction], int]:
    clauses: list[str] = []
    params: list[Any] = []
    if category:
        clauses.append("category = ?")
        params.append(category)
    if account:
        clauses.append("account = ?")
        params.append(account)
    if date_from:
        clauses.append("date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("date <= ?")
        params.append(date_to)
    if min_amount_cents is not None:
        clauses.append("amount_cents >= ?")
        params.append(min_amount_cents)
    if max_amount_cents is not None:
        clauses.append("amount_cents <= ?")
        params.append(max_amount_cents)
    if merchant_search:
        clauses.append("merchant LIKE ?")
        params.append(f"%{merchant_search}%")
    if not include_transfers:
        clauses.append("is_transfer = 0")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    # sort_by/sort_dir come from query params -- validate against an allow
    # list rather than interpolating them straight into SQL.
    sort_columns = {
        "date": "date", "amount": "amount_cents", "merchant": "merchant",
        "category": "category", "account": "account",
    }
    column = sort_columns.get(sort_by, "date")
    direction = "ASC" if sort_dir.lower() == "asc" else "DESC"

    with get_connection(db_path) as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM transactions {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM transactions {where} ORDER BY {column} {direction}, id LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
        return [_row_to_transaction(r) for r in rows], total


def get_uncategorized_transactions(db_path: Path) -> list[Transaction]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE category_source = 'uncategorized' ORDER BY date"
        ).fetchall()
        return [_row_to_transaction(r) for r in rows]


def set_transaction_category(
    db_path: Path,
    tx_id: str,
    *,
    category: str,
    subcategory: str | None,
    confidence: float | None,
    is_transfer: bool,
    category_source: str,
) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            UPDATE transactions
            SET category = ?, subcategory = ?, confidence = ?, is_transfer = ?,
                category_source = ?, updated_at = ?
            WHERE id = ?
            """,
            (category, subcategory, confidence, int(is_transfer), category_source, now_iso(), tx_id),
        )


def set_category_for_merchant(
    db_path: Path,
    merchant_normalized: str,
    *,
    category: str,
    subcategory: str | None,
    exclude_manual: bool = True,
) -> int:
    """Retroactively apply a category to every transaction for this merchant
    that hasn't itself been manually overridden. Used by manual corrections so
    the user doesn't have to re-correct the same merchant across history."""
    with get_connection(db_path) as conn:
        query = """
            UPDATE transactions
            SET category = ?, subcategory = ?, category_source = 'manual', updated_at = ?
            WHERE merchant_normalized = ?
        """
        params: list[Any] = [category, subcategory, now_iso(), merchant_normalized]
        if exclude_manual:
            query += " AND category_source != 'manual'"
        cur = conn.execute(query, params)
        return cur.rowcount


# --- category cache --------------------------------------------------------

def get_category_cache(db_path: Path, merchant_normalized: str) -> dict[str, Any] | None:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM category_cache WHERE merchant_normalized = ?", (merchant_normalized,)
        ).fetchone()
        return dict(row) if row else None


def get_category_cache_bulk(db_path: Path, merchant_normalized_list: list[str]) -> dict[str, dict[str, Any]]:
    if not merchant_normalized_list:
        return {}
    with get_connection(db_path) as conn:
        placeholders = ",".join("?" for _ in merchant_normalized_list)
        rows = conn.execute(
            f"SELECT * FROM category_cache WHERE merchant_normalized IN ({placeholders})",
            merchant_normalized_list,
        ).fetchall()
        return {r["merchant_normalized"]: dict(r) for r in rows}


def upsert_category_cache(
    db_path: Path,
    merchant_normalized: str,
    *,
    category: str,
    subcategory: str | None,
    confidence: float | None,
    is_transfer: bool,
    source: str,
    sample_merchant: str,
) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO category_cache (
                merchant_normalized, category, subcategory, confidence, is_transfer,
                source, sample_merchant, hit_count, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(merchant_normalized) DO UPDATE SET
                category = excluded.category,
                subcategory = excluded.subcategory,
                confidence = excluded.confidence,
                is_transfer = excluded.is_transfer,
                source = excluded.source,
                sample_merchant = excluded.sample_merchant,
                hit_count = category_cache.hit_count + 1,
                updated_at = excluded.updated_at
            """,
            (
                merchant_normalized, category, subcategory, confidence, int(is_transfer),
                source, sample_merchant, now_iso(),
            ),
        )


# --- reconciliation --------------------------------------------------------

def upsert_reconciliation(
    db_path: Path,
    file_id: int,
    *,
    statement_opening_cents: int | None,
    statement_closing_cents: int | None,
    statement_total_debits_cents: int | None,
    statement_total_credits_cents: int | None,
    computed_sum_cents: int,
    delta_cents: int,
    status: str,
    detail: str | None,
) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO reconciliation (
                file_id, statement_opening_cents, statement_closing_cents,
                statement_total_debits_cents, statement_total_credits_cents,
                computed_sum_cents, delta_cents, status, detail, checked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
                statement_opening_cents = excluded.statement_opening_cents,
                statement_closing_cents = excluded.statement_closing_cents,
                statement_total_debits_cents = excluded.statement_total_debits_cents,
                statement_total_credits_cents = excluded.statement_total_credits_cents,
                computed_sum_cents = excluded.computed_sum_cents,
                delta_cents = excluded.delta_cents,
                status = excluded.status,
                detail = excluded.detail,
                checked_at = excluded.checked_at
            """,
            (
                file_id, statement_opening_cents, statement_closing_cents,
                statement_total_debits_cents, statement_total_credits_cents,
                computed_sum_cents, delta_cents, status, detail, now_iso(),
            ),
        )


def get_reconciliation_warnings(db_path: Path) -> list[dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT r.*, f.filename
            FROM reconciliation r
            JOIN files f ON f.id = r.file_id
            WHERE r.status != 'ok'
            ORDER BY r.checked_at
            """
        ).fetchall()
        return [dict(r) for r in rows]


# --- period summary cache --------------------------------------------------

def get_period_summary(db_path: Path, period: str) -> dict[str, Any] | None:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM period_summary WHERE period = ?", (period,)).fetchone()
        return dict(row) if row else None


def set_period_summary(db_path: Path, period: str, *, narrative_markdown: str | None, stats_json: str) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO period_summary (period, narrative_markdown, stats_json, generated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(period) DO UPDATE SET
                narrative_markdown = excluded.narrative_markdown,
                stats_json = excluded.stats_json,
                generated_at = excluded.generated_at
            """,
            (period, narrative_markdown, stats_json, now_iso()),
        )
