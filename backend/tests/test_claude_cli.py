from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

from backend.llm import claude_cli
from backend.llm.provider import strip_markdown_fences


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def test_check_auth_uses_auth_status_when_it_works() -> None:
    with patch("backend.llm.claude_cli.shutil.which", return_value="/usr/bin/claude"), \
         patch("backend.llm.claude_cli.subprocess.run", return_value=_completed(0, stdout="Logged in as jane@example.com")):
        status = claude_cli.check_auth(use_cache=False)
    assert status.state == "authenticated"


def test_check_auth_falls_back_to_functional_probe_on_unknown_subcommand() -> None:
    envelope = json.dumps({"result": "OK"})
    responses = [
        _completed(1, stdout="", stderr="error: unknown command 'auth'"),
        _completed(0, stdout=envelope),
    ]

    def fake_run(*args, **kwargs):
        return responses.pop(0)

    with patch("backend.llm.claude_cli.shutil.which", return_value="/usr/bin/claude"), \
         patch("backend.llm.claude_cli.subprocess.run", side_effect=fake_run):
        status = claude_cli.check_auth(use_cache=False)
    assert status.state == "authenticated"


def test_check_auth_unavailable_when_binary_missing() -> None:
    with patch("backend.llm.claude_cli.shutil.which", return_value=None):
        status = claude_cli.check_auth(use_cache=False)
    assert status.state == "unavailable"


def test_check_auth_unauthenticated_when_not_logged_in() -> None:
    with patch("backend.llm.claude_cli.shutil.which", return_value="/usr/bin/claude"), \
         patch("backend.llm.claude_cli.subprocess.run", return_value=_completed(1, stderr="Not logged in. Please run `claude login`.")):
        status = claude_cli.check_auth(use_cache=False)
    assert status.state == "unauthenticated"


def test_strip_fences_removes_markdown_json_fence() -> None:
    assert strip_markdown_fences('```json\n[{"a": 1}]\n```') == '[{"a": 1}]'


def test_complete_retries_once_then_raises() -> None:
    with patch("backend.llm.claude_cli.shutil.which", return_value="/usr/bin/claude"), \
         patch("backend.llm.claude_cli.subprocess.run", return_value=_completed(1, stderr="boom")) as mock_run:
        provider = claude_cli.ClaudeCLIProvider()
        try:
            provider.complete("hello")
            assert False, "expected ClaudeCLIError"
        except claude_cli.ClaudeCLIError:
            pass
    assert mock_run.call_count == 2  # initial attempt + one retry
