"""FastAPI app + routes. Binds to 127.0.0.1 only (see run.sh) -- no auth,
no login screen, by design (single local user)."""
from __future__ import annotations

import asyncio
import csv
import io
import json
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend import db, jobs
from backend.config import settings
from backend.ingest.discover import discover_files
from backend.ingest.normalize import build_transactions, derive_account_from_filename
from backend.ingest.parse_csv import parse_tabular_file
from backend.ingest.parse_pdf import parse_pdf_file
from backend.ingest.reconcile import reconcile_file
from backend.llm.categorize import categorize_all, extract_pdf_transactions
from backend.llm.provider import check_provider_auth, get_provider
from backend.llm.summarize import compute_summary_stats, generate_narrative
from backend.models import CategoryPatch, HealthResponse, SummaryPayload, Transaction


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db(settings.db_path)
    yield


app = FastAPI(title="Ledger", lifespan=lifespan)


# --- health ---------------------------------------------------------------

@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    dir_exists = settings.statements_dir.exists()
    file_count = len(discover_files(settings.statements_dir)) if dir_exists else 0
    auth = check_provider_auth(settings.llm_provider)
    return HealthResponse(
        status="ok",
        statements_dir=str(settings.statements_dir),
        dir_exists=dir_exists,
        file_count=file_count,
        llm_provider=settings.llm_provider,
        llm_authenticated=auth.ok,
        llm_auth_detail=auth.detail,
    )


# --- ingest (stages 1-3) ---------------------------------------------------

@app.post("/api/ingest")
async def start_ingest() -> dict:
    job = jobs.create_job("ingest")
    task = asyncio.create_task(asyncio.to_thread(_run_ingest_sync, job))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return {"job_id": job.id}


@app.get("/api/ingest/status")
async def ingest_status(job_id: str | None = None) -> StreamingResponse:
    job = jobs.get_job(job_id) if job_id else jobs.get_latest_job("ingest")
    if job is None:
        raise HTTPException(404, "No ingest job found. Start one with POST /api/ingest first.")
    return StreamingResponse(jobs.stream_job_events(job), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _run_ingest_sync(job: jobs.JobState) -> None:
    try:
        db.init_db(settings.db_path)
        job.emit({"type": "progress", "stage": "discover", "message": f"Scanning {settings.statements_dir}"})

        if not settings.statements_dir.exists():
            job.emit({"type": "error", "message": f"Statements folder not found: {settings.statements_dir}"})
            return

        discovered = discover_files(settings.statements_dir)
        total = len(discovered)
        job.emit({"type": "progress", "stage": "discover", "current": total, "total": total, "message": f"Found {total} file(s)"})

        provider = None
        new_files = 0
        new_tx_count = 0
        errors: list[dict] = []

        for i, f in enumerate(discovered, start=1):
            if db.get_file_by_hash(settings.db_path, f.sha256) is not None:
                job.emit({"type": "progress", "stage": "extract", "current": i, "total": total, "message": f"{f.filename}: already ingested"})
                continue

            file_id = db.insert_file(
                settings.db_path, path=str(f.path), filename=f.filename, size_bytes=f.size_bytes,
                mtime=f.mtime, sha256=f.sha256, file_type=f.file_type,
            )
            job.emit({"type": "progress", "stage": "extract", "current": i, "total": total, "message": f"Reading {f.filename}"})

            try:
                if f.file_type == "pdf":
                    if provider is None:
                        provider = get_provider(settings.llm_provider, model=settings.categorize_model)

                    def llm_fallback(page_text: str, _provider=provider):
                        return extract_pdf_transactions(page_text, _provider)

                    parsed, page_results = parse_pdf_file(f.path, llm_fallback=llm_fallback)
                    account = parsed.account_hint or derive_account_from_filename(f.filename)
                    transactions: list[Transaction] = []
                    for pr in page_results:
                        transactions.extend(
                            build_transactions(pr.transactions, account=account, source_file=f.filename, extraction_method=pr.extraction_method)
                        )
                elif f.file_type in ("csv", "ofx", "qfx"):
                    parsed = parse_tabular_file(f.path, f.file_type)
                    account = parsed.account_hint or derive_account_from_filename(f.filename)
                    transactions = build_transactions(parsed.transactions, account=account, source_file=f.filename, extraction_method="csv")
                else:
                    raise ValueError(f"unsupported file type: {f.file_type}")

                inserted = db.insert_transactions(settings.db_path, file_id, transactions)
                db.set_file_statement_balances(
                    settings.db_path, file_id,
                    opening_cents=db.to_cents(parsed.opening_balance) if parsed.opening_balance is not None else None,
                    closing_cents=db.to_cents(parsed.closing_balance) if parsed.closing_balance is not None else None,
                    total_debits_cents=db.to_cents(parsed.total_debits) if parsed.total_debits is not None else None,
                    total_credits_cents=db.to_cents(parsed.total_credits) if parsed.total_credits is not None else None,
                )
                db.update_file_status(settings.db_path, file_id, status="extracted", transaction_count=inserted, account=account, mark_extracted=True)
                new_files += 1
                new_tx_count += inserted
                job.emit({"type": "progress", "stage": "extract", "current": i, "total": total, "message": f"{f.filename}: {inserted} transaction(s)"})
            except Exception as e:  # noqa: BLE001 -- one bad file must not kill the run
                db.update_file_status(settings.db_path, file_id, status="failed", error_message=str(e))
                errors.append({"file": f.filename, "error": str(e)})
                job.emit({"type": "progress", "stage": "extract", "current": i, "total": total, "message": f"{f.filename}: failed -- {e}"})

        job.emit({
            "type": "done",
            "message": f"Ingested {new_files} new file(s), {new_tx_count} new transaction(s).",
            "current": total, "total": total,
        })
    except Exception as e:  # noqa: BLE001
        job.emit({"type": "error", "message": str(e)})


# --- analyze (stages 4-5 + narrative) --------------------------------------

@app.post("/api/analyze")
async def start_analyze(period: str | None = None) -> dict:
    job = jobs.create_job("analyze")
    task = asyncio.create_task(asyncio.to_thread(_run_analyze_sync, job, period))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return {"job_id": job.id}


@app.get("/api/analyze/status")
async def analyze_status(job_id: str | None = None) -> StreamingResponse:
    job = jobs.get_job(job_id) if job_id else jobs.get_latest_job("analyze")
    if job is None:
        raise HTTPException(404, "No analyze job found. Start one with POST /api/analyze first.")
    return StreamingResponse(jobs.stream_job_events(job), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


def _default_period() -> str | None:
    all_tx = db.get_all_transactions(settings.db_path)
    if not all_tx:
        return None
    latest = max(t.date for t in all_tx)
    return f"{latest.year:04d}-{latest.month:02d}"


def _run_analyze_sync(job: jobs.JobState, period: str | None) -> None:
    try:
        db.init_db(settings.db_path)

        auth = check_provider_auth(settings.llm_provider)
        if not auth.ok:
            job.emit({
                "type": "error",
                "message": f"LLM provider '{settings.llm_provider}' is not ready: {auth.detail}",
            })
            return

        job.emit({"type": "progress", "stage": "categorize", "message": "Categorizing transactions"})
        categorize_provider = get_provider(settings.llm_provider, model=settings.categorize_model)
        uncategorized = db.get_uncategorized_transactions(settings.db_path)

        def on_progress(completed: int, total: int) -> None:
            job.emit({"type": "progress", "stage": "categorize", "current": completed, "total": total})

        categorize_all(settings.db_path, uncategorized, categorize_provider, on_progress=on_progress)

        job.emit({"type": "progress", "stage": "reconcile", "message": "Checking statement balances"})
        files = db.list_files(settings.db_path)
        for i, file_row in enumerate(files, start=1):
            if file_row["status"] == "extracted":
                reconcile_file(settings.db_path, file_row["id"])
            job.emit({"type": "progress", "stage": "reconcile", "current": i, "total": len(files)})

        resolved_period = period or _default_period()
        if resolved_period is None:
            job.emit({"type": "error", "message": "No transactions found. Run ingest first."})
            return

        job.emit({"type": "progress", "stage": "narrative", "message": f"Writing summary for {resolved_period}"})
        stats = compute_summary_stats(settings.db_path, resolved_period)
        narrative_provider = get_provider(settings.llm_provider, model=settings.narrative_model)
        narrative = generate_narrative(stats, narrative_provider)

        stats_json = json.dumps({k: v for k, v in stats.items() if isinstance(v, (str, int, float))})
        db.set_period_summary(settings.db_path, resolved_period, narrative_markdown=narrative, stats_json=stats_json)

        job.emit({"type": "done", "message": "Analysis complete.", "data": {"period": resolved_period}})
    except Exception as e:  # noqa: BLE001
        job.emit({"type": "error", "message": str(e)})


# --- summary / transactions -------------------------------------------------

@app.get("/api/summary", response_model=SummaryPayload)
def get_summary(period: str | None = None) -> SummaryPayload:
    resolved_period = period or _default_period()
    if resolved_period is None:
        raise HTTPException(404, "No data yet. Read statements first.")

    stats = compute_summary_stats(settings.db_path, resolved_period)
    cached = db.get_period_summary(settings.db_path, resolved_period)
    narrative = cached["narrative_markdown"] if cached else None

    return SummaryPayload(
        period=resolved_period,
        total_in=stats["total_in"],
        total_out=stats["total_out"],
        net=stats["net"],
        transaction_count=stats["transaction_count"],
        days_covered=stats["days_covered"],
        category_totals=stats["category_totals"],
        top_merchants=stats["top_merchants"],
        largest_transactions=stats["largest_transactions"],
        daily_series=stats["daily_series"],
        recurring_charges=stats["recurring_charges"],
        reconciliation_warnings=stats["reconciliation_warnings"],
        narrative_markdown=narrative,
    )


@app.get("/api/transactions")
def list_transactions(
    category: str | None = None,
    account: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_amount: str | None = None,
    max_amount: str | None = None,
    merchant: str | None = None,
    include_transfers: bool = True,
    sort_by: str = "date",
    sort_dir: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> dict:
    def to_cents_or_none(raw: str | None) -> int | None:
        if raw is None:
            return None
        try:
            return db.to_cents(Decimal(raw))
        except InvalidOperation:
            raise HTTPException(400, f"Invalid amount: {raw!r}")

    rows, total = db.query_transactions(
        settings.db_path,
        category=category, account=account, date_from=date_from, date_to=date_to,
        min_amount_cents=to_cents_or_none(min_amount), max_amount_cents=to_cents_or_none(max_amount),
        merchant_search=merchant, include_transfers=include_transfers,
        sort_by=sort_by, sort_dir=sort_dir, page=page, page_size=page_size,
    )
    return {
        "transactions": [t.model_dump(mode="json") for t in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@app.patch("/api/transactions/{tx_id}")
def patch_transaction(tx_id: str, patch: CategoryPatch) -> dict:
    tx = db.get_transaction(settings.db_path, tx_id)
    if tx is None:
        raise HTTPException(404, f"No transaction with id {tx_id}")

    db.set_transaction_category(
        settings.db_path, tx_id, category=patch.category, subcategory=patch.subcategory,
        confidence=1.0, is_transfer=tx.is_transfer, category_source="manual",
    )
    db.upsert_category_cache(
        settings.db_path, tx.merchant_normalized, category=patch.category, subcategory=patch.subcategory,
        confidence=1.0, is_transfer=tx.is_transfer, source="manual", sample_merchant=tx.merchant,
    )
    propagated = db.set_category_for_merchant(
        settings.db_path, tx.merchant_normalized, category=patch.category, subcategory=patch.subcategory,
    )

    updated = db.get_transaction(settings.db_path, tx_id)
    return {"transaction": updated.model_dump(mode="json"), "propagated_to": propagated}


@app.get("/api/export")
def export_data(format: str = Query(..., pattern="^(csv|md)$"), period: str | None = None):
    if format == "csv":
        rows = db.get_all_transactions(settings.db_path)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["date", "merchant", "description", "amount", "category", "subcategory", "account", "is_transfer", "extraction_method"])
        for t in rows:
            writer.writerow([t.date.isoformat(), t.merchant, t.description, str(t.amount), t.category or "", t.subcategory or "", t.account, t.is_transfer, t.extraction_method])
        return StreamingResponse(
            iter([buffer.getvalue()]), media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=ledger_transactions.csv"},
        )

    resolved_period = period or _default_period()
    if resolved_period is None:
        raise HTTPException(404, "No data yet. Read statements first.")
    cached = db.get_period_summary(settings.db_path, resolved_period)
    narrative = cached["narrative_markdown"] if cached else "_No narrative generated yet. Run Generate summary first._"
    stats = compute_summary_stats(settings.db_path, resolved_period)

    lines = [f"# Ledger report -- {resolved_period}", ""]
    lines.append(f"**Total out:** {stats['total_out']}  ")
    lines.append(f"**Total in:** {stats['total_in']}  ")
    lines.append(f"**Net:** {stats['net']}")
    lines.append("")
    lines.append("## Category breakdown")
    for c in stats["category_totals"]:
        lines.append(f"- {c.category}: {c.total} ({c.percent:.1f}%)")
    lines.append("")
    lines.append("## Summary")
    lines.append(narrative)
    content = "\n".join(lines)

    return StreamingResponse(
        iter([content]), media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=ledger_report_{resolved_period}.md"},
    )


# --- static frontend (prod mode) --------------------------------------------
# Registered LAST so it never shadows an /api/* route above.

_DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_DIST_DIR), html=True), name="frontend")
