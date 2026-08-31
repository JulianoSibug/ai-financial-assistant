from __future__ import annotations

from pathlib import Path

import pytest

from backend import db


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test_ledger.db"
    db.init_db(path)
    return path
