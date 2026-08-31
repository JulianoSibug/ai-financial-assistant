"""Stage 1: walk STATEMENTS_DIR, list files, hash for dedup."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

PDF_EXTENSIONS = {".pdf"}
CSV_EXTENSIONS = {".csv"}
OFX_EXTENSIONS = {".ofx"}
QFX_EXTENSIONS = {".qfx"}


@dataclass
class DiscoveredFile:
    path: Path
    filename: str
    size_bytes: int
    mtime: float
    sha256: str
    file_type: str  # 'pdf' | 'csv' | 'ofx' | 'qfx' | 'unknown'


def classify_file_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in PDF_EXTENSIONS:
        return "pdf"
    if suffix in CSV_EXTENSIONS:
        return "csv"
    if suffix in OFX_EXTENSIONS:
        return "ofx"
    if suffix in QFX_EXTENSIONS:
        return "qfx"
    return "unknown"


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_files(statements_dir: Path) -> list[DiscoveredFile]:
    """Recursively walk statements_dir (so a parent folder containing
    multiple month subfolders works too), skipping hidden files/dirs and
    anything that isn't a recognized statement format."""
    if not statements_dir.exists():
        return []

    results: list[DiscoveredFile] = []
    for path in sorted(statements_dir.rglob("*")):
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.relative_to(statements_dir).parts):
            continue
        file_type = classify_file_type(path)
        if file_type == "unknown":
            continue
        stat = path.stat()
        results.append(
            DiscoveredFile(
                path=path,
                filename=path.name,
                size_bytes=stat.st_size,
                mtime=stat.st_mtime,
                sha256=hash_file(path),
                file_type=file_type,
            )
        )
    return results
