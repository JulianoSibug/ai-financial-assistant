"""In-memory job state for /api/ingest and /api/analyze progress streaming.

No persistence needed: jobs are short-lived, and both pipelines are already
idempotent (hash-based file dedup, category cache), so losing job state on a
restart just means the user re-triggers -- nothing is lost or double-counted.
"""
from __future__ import annotations

import asyncio
import json
import queue
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class JobState:
    id: str
    kind: str  # "ingest" | "analyze"
    events: "queue.Queue[dict[str, Any]]" = field(default_factory=queue.Queue)
    finished: bool = False
    terminal_event: dict[str, Any] | None = None

    def emit(self, event: dict[str, Any]) -> None:
        self.events.put(event)
        if event.get("type") in ("done", "error"):
            self.finished = True
            self.terminal_event = event


_JOBS: dict[str, JobState] = {}
_LATEST_JOB_BY_KIND: dict[str, str] = {}


def create_job(kind: str) -> JobState:
    job = JobState(id=str(uuid.uuid4()), kind=kind)
    _JOBS[job.id] = job
    _LATEST_JOB_BY_KIND[kind] = job.id
    return job


def get_job(job_id: str) -> JobState | None:
    return _JOBS.get(job_id)


def get_latest_job(kind: str) -> JobState | None:
    job_id = _LATEST_JOB_BY_KIND.get(kind)
    return _JOBS.get(job_id) if job_id else None


async def stream_job_events(job: JobState) -> AsyncIterator[str]:
    """SSE generator. Drains the queue first and only consults `finished`
    once it's empty, so a terminal event already queued when the job
    finishes is never lost to a race between the two."""
    if job.finished and job.terminal_event is not None and job.events.empty():
        yield f"data: {json.dumps(job.terminal_event)}\n\n"
        return

    while True:
        try:
            event = job.events.get_nowait()
        except queue.Empty:
            if job.finished:
                return
            await asyncio.sleep(0.25)
            continue
        yield f"data: {json.dumps(event)}\n\n"
        if event.get("type") in ("done", "error"):
            return
