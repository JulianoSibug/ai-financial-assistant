"""Environment loading and resolved paths. Single source of truth for config."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

# Default model IDs, used unless ANTHROPIC_MODEL overrides both.
DEFAULT_CATEGORIZE_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_NARRATIVE_MODEL = "claude-sonnet-5"

CATEGORIES: list[str] = [
    "Housing",
    "Utilities",
    "Groceries",
    "Dining & Takeout",
    "Transportation",
    "Fuel",
    "Health & Fitness",
    "Insurance",
    "Subscriptions",
    "Shopping",
    "Entertainment",
    "Travel",
    "Education",
    "Personal Care",
    "Gifts & Donations",
    "Fees & Interest",
    "Taxes",
    "Income",
    "Transfers",
    "Uncategorized",
]


def _resolve_statements_dir() -> Path:
    raw = os.environ.get("STATEMENTS_DIR", "~/Documents/Financial Statements/Aug 2026")
    return Path(raw).expanduser().resolve()


def _resolve_db_path() -> Path:
    raw = os.environ.get("DB_PATH", "data/ledger.db")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


class Settings:
    """Re-reads nothing at runtime; instantiate once at import time.

    STATEMENTS_DIR is read lazily via a property so tests can monkeypatch the
    env var before Settings() is constructed.
    """

    def __init__(self) -> None:
        self.statements_dir: Path = _resolve_statements_dir()
        self.db_path: Path = _resolve_db_path()
        self.llm_provider: str = os.environ.get("LLM_PROVIDER", "claude_cli").strip().lower()
        self.anthropic_api_key: str | None = os.environ.get("ANTHROPIC_API_KEY") or None
        self.anthropic_model_override: str | None = os.environ.get("ANTHROPIC_MODEL") or None
        self.host: str = os.environ.get("HOST", "127.0.0.1")
        self.port: int = int(os.environ.get("PORT", "8000"))

    @property
    def categorize_model(self) -> str:
        return self.anthropic_model_override or DEFAULT_CATEGORIZE_MODEL

    @property
    def narrative_model(self) -> str:
        return self.anthropic_model_override or DEFAULT_NARRATIVE_MODEL


settings = Settings()
