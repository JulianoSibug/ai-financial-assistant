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
