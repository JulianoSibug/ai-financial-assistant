"""Default LLM provider: shells out to the Claude Code CLI in headless mode,
so categorization/narrative calls run on the user's Claude Pro subscription
instead of metered API billing.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time

from backend.llm.provider import AuthStatus, strip_markdown_fences

_AUTH_CACHE_TTL_SECONDS = 60
_auth_cache: tuple[float, AuthStatus] | None = None


class ClaudeCLIError(RuntimeError):
    pass


def _run_claude_once(prompt: str, *, max_turns: int = 1, timeout: int = 180) -> str:
    binary = shutil.which("claude")
    if not binary:
        raise ClaudeCLIError("claude CLI not found on PATH.")

    proc = subprocess.run(
        [binary, "-p", "--output-format", "json", "--allowedTools", "", "--max-turns", str(max_turns)],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise ClaudeCLIError(f"claude exited {proc.returncode}: {proc.stderr.strip()[:500]}")

    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise ClaudeCLIError(f"claude returned non-JSON output: {e}") from e

    result = envelope.get("result")
    if not result:
        raise ClaudeCLIError(f"claude JSON envelope had no 'result' field: {envelope!r}")
    return strip_markdown_fences(result)


class ClaudeCLIProvider:
    """Retries once on a non-zero exit or unparseable output -- a single bad
    batch shouldn't kill the whole ingest/analyze run, but a transient
    hiccup shouldn't fail it either. The caller (categorize.py) is
    responsible for catching a second failure and marking just that batch
    failed rather than aborting the run."""

    def complete(self, prompt: str, max_tokens: int = 4096) -> str:
        try:
            return _run_claude_once(prompt)
        except (ClaudeCLIError, subprocess.TimeoutExpired):
            return _run_claude_once(prompt)


_NEGATIVE_AUTH_MARKERS = ("not logged in", "not authenticated", "please run", "login", "unauthorized", "401")
_UNKNOWN_SUBCOMMAND_MARKERS = ("unknown command", "unrecognized", "unknown subcommand", "usage:", "invalid command")


def check_auth(*, use_cache: bool = True) -> AuthStatus:
    """Run at app startup (and before /api/analyze) to fail fast with a clear
    message rather than let the app half-work. Cached briefly so GET
    /api/health polling doesn't spawn a subprocess on every request."""
    global _auth_cache
    if use_cache and _auth_cache is not None:
        checked_at, status = _auth_cache
        if time.monotonic() - checked_at < _AUTH_CACHE_TTL_SECONDS:
            return status

    status = _check_auth_uncached()
    _auth_cache = (time.monotonic(), status)
    return status


def _check_auth_uncached() -> AuthStatus:
    binary = shutil.which("claude")
    if not binary:
        return AuthStatus("unavailable", "claude CLI not found on PATH.")

    try:
        r = subprocess.run([binary, "auth", "status"], capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, OSError) as e:
        return AuthStatus("unavailable", f"could not run 'claude auth status': {e}")

    combined = (r.stdout + r.stderr).lower()
    if any(marker in combined for marker in _UNKNOWN_SUBCOMMAND_MARKERS):
        # 'claude auth status' isn't a real subcommand on this CLI version --
        # fall back to a minimal functional probe instead of guessing.
        return _functional_probe(binary)
    if r.returncode == 0 and not any(marker in combined for marker in _NEGATIVE_AUTH_MARKERS):
        return AuthStatus("authenticated", r.stdout.strip()[:500])
    return AuthStatus("unauthenticated", combined.strip()[:500])


def _functional_probe(binary: str) -> AuthStatus:
    """Runs the exact minimal invocation the app uses in production and
    checks whether it behaves like a logged-in call."""
    try:
        r = subprocess.run(
            [binary, "-p", "--output-format", "json", "--allowedTools", "", "--max-turns", "1"],
            input="Reply with exactly: OK",
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return AuthStatus("unavailable", f"functional probe failed to run: {e}")

    if r.returncode == 0:
        try:
            envelope = json.loads(r.stdout)
            if envelope.get("result"):
                return AuthStatus("authenticated", "functional probe succeeded")
        except json.JSONDecodeError:
            pass

    combined = (r.stdout + r.stderr).lower()
    if any(marker in combined for marker in _NEGATIVE_AUTH_MARKERS):
        return AuthStatus("unauthenticated", combined.strip()[:500])
    return AuthStatus("unavailable", f"claude CLI did not behave as expected (exit {r.returncode}).")
