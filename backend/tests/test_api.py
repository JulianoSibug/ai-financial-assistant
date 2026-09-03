from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.tests.fixtures.build_fixtures import FixtureTransaction, make_csv_statement


@pytest.fixture
def api_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    statements_dir = tmp_path / "statements"
    statements_dir.mkdir()
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "statements_dir", statements_dir)
    monkeypatch.setattr(settings, "db_path", db_path)
    return statements_dir


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_reports_missing_dir(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "statements_dir", tmp_path / "does-not-exist")
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")

    resp = client.get("/api/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["dir_exists"] is False
    assert body["file_count"] == 0
    assert "does-not-exist" in body["statements_dir"]


def test_health_reports_existing_dir_with_files(client: TestClient, api_env: Path) -> None:
    make_csv_statement(
        api_env / "checking.csv",
        [FixtureTransaction(date(2026, 8, 1), "COFFEE SHOP", Decimal("-5.00"))],
    )
    resp = client.get("/api/health")
    body = resp.json()
    assert body["dir_exists"] is True
    assert body["file_count"] == 1


def test_full_ingest_pipeline_via_sse(client: TestClient, api_env: Path) -> None:
    make_csv_statement(
        api_env / "checking_aug.csv",
        [
            FixtureTransaction(date(2026, 8, 1), "STARBUCKS #4471", Decimal("-4.75")),
            FixtureTransaction(date(2026, 8, 3), "PAYCHECK DEPOSIT", Decimal("2000.00")),
            FixtureTransaction(date(2026, 8, 5), "WHOLE FOODS MARKET", Decimal("-86.42")),
        ],
        opening_balance=Decimal("1000.00"),
    )

    start_resp = client.post("/api/ingest")
    assert start_resp.status_code == 200
    job_id = start_resp.json()["job_id"]

    with client.stream("GET", f"/api/ingest/status?job_id={job_id}") as stream:
        events = [line for line in stream.iter_lines() if line.startswith("data:")]

    assert any('"type": "done"' in e or '"type":"done"' in e for e in events)

    tx_resp = client.get("/api/transactions")
    assert tx_resp.status_code == 200
    body = tx_resp.json()
    assert body["total"] == 3


def test_patch_transaction_manual_override(client: TestClient, api_env: Path) -> None:
    make_csv_statement(
        api_env / "checking.csv",
        [FixtureTransaction(date(2026, 8, 1), "WIDGET CO PAYMENT", Decimal("-20.00"))],
    )
    client.post("/api/ingest")
    with client.stream("GET", "/api/ingest/status") as stream:
        list(stream.iter_lines())

    tx_id = client.get("/api/transactions").json()["transactions"][0]["id"]

    patch_resp = client.patch(f"/api/transactions/{tx_id}", json={"category": "Shopping"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["transaction"]["category"] == "Shopping"

    refetched = client.get("/api/transactions").json()["transactions"][0]
    assert refetched["category"] == "Shopping"


def test_patch_transaction_rejects_unknown_category(client: TestClient, api_env: Path) -> None:
    make_csv_statement(
        api_env / "checking.csv",
        [FixtureTransaction(date(2026, 8, 1), "SOMETHING", Decimal("-10.00"))],
    )
    client.post("/api/ingest")
    with client.stream("GET", "/api/ingest/status") as stream:
        list(stream.iter_lines())
    tx_id = client.get("/api/transactions").json()["transactions"][0]["id"]

    resp = client.patch(f"/api/transactions/{tx_id}", json={"category": "Not A Real Category"})
    assert resp.status_code == 422


def test_export_csv(client: TestClient, api_env: Path) -> None:
    make_csv_statement(
        api_env / "checking.csv",
        [FixtureTransaction(date(2026, 8, 1), "COFFEE SHOP", Decimal("-5.00"))],
    )
    client.post("/api/ingest")
    with client.stream("GET", "/api/ingest/status") as stream:
        list(stream.iter_lines())

    resp = client.get("/api/export?format=csv")
    assert resp.status_code == 200
    assert "Coffee Shop" in resp.text


def _write_mismatched_csv(path: Path) -> None:
    """A statement whose declared closing balance doesn't match opening +
    transactions -- parse_csv.py derives opening_balance from the first row's
    balance minus its amount, and closing_balance literally off the last
    row's balance, so a wrong final balance produces a genuine mismatch."""
    path.write_text(
        "Date,Description,Amount,Balance\n"
        "08/01/2026,SOMETHING,-20.00,980.00\n"
        "08/02/2026,SOMETHING ELSE,-30.00,500.00\n"
    )


def test_ingest_flags_reconciliation_warning_without_generate_summary(client: TestClient, api_env: Path) -> None:
    """Detection must be automatic -- a bad statement should be queued for
    review right after ingest, with no need to click Generate Summary first."""
    _write_mismatched_csv(api_env / "checking.csv")

    client.post("/api/ingest")
    with client.stream("GET", "/api/ingest/status") as stream:
        list(stream.iter_lines())

    resp = client.get("/api/fix-requests")
    assert resp.status_code == 200
    fix_requests = resp.json()["fix_requests"]
    assert len(fix_requests) == 1
    assert fix_requests[0]["trigger"] == "reconciliation_warning"
    assert fix_requests[0]["filename"] == "checking.csv"


def test_patch_fix_request_resolves_and_removes_it_from_open_list(client: TestClient, api_env: Path) -> None:
    _write_mismatched_csv(api_env / "checking.csv")
    client.post("/api/ingest")
    with client.stream("GET", "/api/ingest/status") as stream:
        list(stream.iter_lines())
    fix_request_id = client.get("/api/fix-requests").json()["fix_requests"][0]["id"]

    resp = client.patch(f"/api/fix-requests/{fix_request_id}", json={"status": "resolved"})
    assert resp.status_code == 200
    assert client.get("/api/fix-requests").json()["fix_requests"] == []


def test_patch_fix_request_rejects_unknown_status(client: TestClient, api_env: Path) -> None:
    _write_mismatched_csv(api_env / "checking.csv")
    client.post("/api/ingest")
    with client.stream("GET", "/api/ingest/status") as stream:
        list(stream.iter_lines())
    fix_request_id = client.get("/api/fix-requests").json()["fix_requests"][0]["id"]

    resp = client.patch(f"/api/fix-requests/{fix_request_id}", json={"status": "not-a-real-status"})
    assert resp.status_code == 422


def test_ingest_categorizes_transactions_without_generate_summary(
    client: TestClient, api_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Categorization must be automatic too -- a freshly-ingested transaction
    for a known merchant should already be labeled, with no need to click
    Generate Summary first."""
    monkeypatch.setattr(settings, "llm_provider", "manual")
    make_csv_statement(
        api_env / "checking.csv",
        [FixtureTransaction(date(2026, 8, 1), "NETFLIX.COM NETFLIX.COM", Decimal("-15.49"))],
    )

    client.post("/api/ingest")
    with client.stream("GET", "/api/ingest/status") as stream:
        list(stream.iter_lines())

    tx = client.get("/api/transactions").json()["transactions"][0]
    assert tx["category"] == "Subscriptions"
    assert tx["category_source"] == "llm"


def test_reingest_of_already_flagged_file_does_not_duplicate_fix_request(client: TestClient, api_env: Path) -> None:
    _write_mismatched_csv(api_env / "checking.csv")
    client.post("/api/ingest")
    with client.stream("GET", "/api/ingest/status") as stream:
        list(stream.iter_lines())

    # Re-running ingest is a no-op for an already-hashed file, and re-running
    # analyze's reconcile backfill on the same still-broken file must not
    # spam a second open request for it.
    client.post("/api/ingest")
    with client.stream("GET", "/api/ingest/status") as stream:
        list(stream.iter_lines())
    client.post("/api/analyze")
    with client.stream("GET", "/api/analyze/status") as stream:
        list(stream.iter_lines())

    fix_requests = client.get("/api/fix-requests").json()["fix_requests"]
    assert len(fix_requests) == 1


def test_periods_lists_every_month_with_data_most_recent_first(client: TestClient, api_env: Path) -> None:
    make_csv_statement(
        api_env / "multi_year.csv",
        [
            FixtureTransaction(date(2024, 9, 15), "OLD PURCHASE", Decimal("-10.00")),
            FixtureTransaction(date(2026, 3, 1), "SPRING PURCHASE", Decimal("-20.00")),
            FixtureTransaction(date(2026, 8, 1), "RECENT PURCHASE", Decimal("-30.00")),
        ],
    )
    client.post("/api/ingest")
    with client.stream("GET", "/api/ingest/status") as stream:
        list(stream.iter_lines())

    resp = client.get("/api/periods")
    assert resp.status_code == 200
    periods = resp.json()["periods"]
    assert [p["period"] for p in periods] == ["2026-08", "2026-03", "2024-09"]
    assert all(p["transaction_count"] == 1 for p in periods)
