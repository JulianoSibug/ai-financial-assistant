from __future__ import annotations

from pathlib import Path

from backend import db


def _make_file(db_path: Path, filename: str = "statement.csv") -> int:
    return db.insert_file(
        db_path, path=f"/tmp/{filename}", filename=filename, size_bytes=1,
        mtime=0.0, sha256=filename, file_type="csv",
    )


def test_create_and_list_fix_request(db_path: Path) -> None:
    file_id = _make_file(db_path)

    db.create_fix_request(db_path, file_id, "reconciliation_warning", "off by $12.34")

    open_requests = db.list_fix_requests(db_path, status="open")
    assert len(open_requests) == 1
    assert open_requests[0]["filename"] == "statement.csv"
    assert open_requests[0]["trigger"] == "reconciliation_warning"
    assert open_requests[0]["signal_detail"] == "off by $12.34"
    assert open_requests[0]["status"] == "open"


def test_create_fix_request_dedupes_open_requests_for_same_file_and_trigger(db_path: Path) -> None:
    """Re-running ingest/analyze on a still-broken file must not spam
    duplicate rows into the review queue."""
    file_id = _make_file(db_path)

    db.create_fix_request(db_path, file_id, "reconciliation_warning", "first detail")
    db.create_fix_request(db_path, file_id, "reconciliation_warning", "second detail")

    open_requests = db.list_fix_requests(db_path, status="open")
    assert len(open_requests) == 1
    assert open_requests[0]["signal_detail"] == "first detail"


def test_resolve_fix_request_removes_it_from_open_list(db_path: Path) -> None:
    file_id = _make_file(db_path)
    db.create_fix_request(db_path, file_id, "low_extraction", "page 2 looks unparsed")
    request_id = db.list_fix_requests(db_path, status="open")[0]["id"]

    db.resolve_fix_request(db_path, request_id, "resolved")

    assert db.list_fix_requests(db_path, status="open") == []
    resolved = db.list_fix_requests(db_path, status="resolved")
    assert len(resolved) == 1
    assert resolved[0]["resolved_at"] is not None


def test_create_fix_request_allows_reopening_after_resolution(db_path: Path) -> None:
    """A different trigger firing again after a prior request was resolved
    is a fresh, legitimate problem -- not a duplicate to suppress."""
    file_id = _make_file(db_path)
    db.create_fix_request(db_path, file_id, "reconciliation_warning", "first")
    request_id = db.list_fix_requests(db_path, status="open")[0]["id"]
    db.resolve_fix_request(db_path, request_id, "resolved")

    db.create_fix_request(db_path, file_id, "reconciliation_warning", "second")

    open_requests = db.list_fix_requests(db_path, status="open")
    assert len(open_requests) == 1
    assert open_requests[0]["signal_detail"] == "second"
