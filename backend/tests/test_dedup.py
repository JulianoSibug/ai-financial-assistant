from __future__ import annotations

from pathlib import Path

from backend import db
from backend.ingest.normalize import build_transactions
from backend.ingest.parse_csv import parse_csv_file


def test_dedup_across_overlapping_statement_files(db_path: Path, tmp_path: Path) -> None:
    """Two monthly exports with one overlapping transaction (banks often
    export slightly overlapping date ranges) must not double-count it."""
    file_a = tmp_path / "checking_aug.csv"
    file_a.write_text(
        "Date,Description,Amount\n"
        "08/29/2026,COFFEE SHOP,-5.00\n"
        "08/30/2026,GROCERY STORE,-60.00\n"
    )
    file_b = tmp_path / "checking_sep.csv"
    file_b.write_text(
        "Date,Description,Amount\n"
        "08/30/2026,GROCERY STORE,-60.00\n"
        "09/01/2026,RENT,-1200.00\n"
    )

    account = "checking"
    total_inserted = 0
    for path in (file_a, file_b):
        parsed = parse_csv_file(path)
        transactions = build_transactions(
            parsed.transactions, account=account, source_file=path.name, extraction_method="csv"
        )
        file_id = db.insert_file(
            db_path, path=str(path), filename=path.name, size_bytes=path.stat().st_size,
            mtime=path.stat().st_mtime, sha256=f"hash-{path.name}", file_type="csv",
        )
        total_inserted += db.insert_transactions(db_path, file_id, transactions)

    all_tx = db.get_all_transactions(db_path)
    assert len(all_tx) == 3  # 2 + 2 rows, one shared -> 3 unique
    assert total_inserted == 3
