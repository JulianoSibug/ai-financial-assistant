"""Pydantic v2 schemas shared across the backend."""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.config import CATEGORIES

ExtractionMethod = Literal["regex", "csv", "llm"]
CategorySource = Literal["llm", "cache", "manual", "rule", "uncategorized"]
ReconciliationStatus = Literal["ok", "warning", "not_applicable"]


class Transaction(BaseModel):
    id: str
    date: datetime.date
    description: str
    merchant: str
    merchant_normalized: str
    amount: Decimal
    account: str
    source_file: str
    extraction_method: ExtractionMethod
    category: str | None = None
    subcategory: str | None = None
    confidence: float | None = None
    is_transfer: bool = False
    category_source: CategorySource = "uncategorized"


class HealthResponse(BaseModel):
    status: str
    statements_dir: str
    dir_exists: bool
    file_count: int
    llm_provider: str
    llm_authenticated: bool
    llm_auth_detail: str | None = None


class ReconciliationWarning(BaseModel):
    file_id: int
    filename: str
    status: ReconciliationStatus
    delta: Decimal
    detail: str | None = None


class RecurringCharge(BaseModel):
    merchant: str
    amount: Decimal | None = None
    cadence: str
    occurrences: int


class CategoryTotal(BaseModel):
    category: str
    total: Decimal
    percent: float
    delta_vs_prior: Decimal | None = None


class MerchantTotal(BaseModel):
    merchant: str
    count: int
    total: Decimal


class DailyPoint(BaseModel):
    date: datetime.date
    total_out: Decimal


class SummaryPayload(BaseModel):
    period: str
    total_in: Decimal
    total_out: Decimal
    net: Decimal
    transaction_count: int
    days_covered: int
    category_totals: list[CategoryTotal]
    top_merchants: list[MerchantTotal]
    largest_transactions: list[Transaction]
    daily_series: list[DailyPoint]
    recurring_charges: list[RecurringCharge]
    reconciliation_warnings: list[ReconciliationWarning]
    narrative_markdown: str | None = None


class JobEvent(BaseModel):
    type: Literal["progress", "done", "error"]
    stage: str | None = None
    message: str | None = None
    current: int | None = None
    total: int | None = None


class CategoryPatch(BaseModel):
    category: str
    subcategory: str | None = None

    @field_validator("category")
    @classmethod
    def category_must_be_valid(cls, v: str) -> str:
        if v not in CATEGORIES:
            raise ValueError(f"category must be one of {CATEGORIES}")
        return v


class FixRequestPatch(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str) -> str:
        if v not in ("resolved", "dismissed"):
            raise ValueError("status must be 'resolved' or 'dismissed'")
        return v


class LLMCategorization(BaseModel):
    """One element of the categorization batch response, validated before use."""

    id: str
    category: str
    subcategory: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    is_transfer: bool = False

    @field_validator("category")
    @classmethod
    def category_must_be_valid(cls, v: str) -> str:
        if v not in CATEGORIES:
            raise ValueError(f"category must be one of {CATEGORIES}")
        return v


class LLMExtractedTransaction(BaseModel):
    """One element of a PDF LLM-extraction-fallback response."""

    date: datetime.date
    description: str
    amount: Decimal
