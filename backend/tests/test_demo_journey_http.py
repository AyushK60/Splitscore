"""Regression test for the live HTTP journey script.

``scripts/demo_journey.py`` verifies the documented user journey against a
*running* server. Its previous version piped each JSON body into curl's stdin
without ever telling curl to read from stdin (no ``-d @-``), so every POST was
transmitted with an empty body. FastAPI then answered::

    422 {"error": {"code": "validation_error", "details": {
        "problems": [{"location": "body", "message": "Field required", "type": "missing"}]}}}

The payload shapes and response field names in that script were also wrong
(``strategies`` entries missing the required ``label``, ``finding.evidence_examples``
instead of ``finding.examples``, ``row.evaluation.entity_overlap_total`` instead of
``row.entity_shared_groups``), which TestClient tests could never catch because
they never ran the script.

This test starts the real application on a real socket and runs the script as a
subprocess over HTTP, so a request body that is not actually transmitted, or a
response field read from the wrong key, fails here.

Run: cd backend && python -m pytest tests/test_demo_journey_http.py -v
"""

from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "demo_journey.py"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _wait_for_health(base_url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=2) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # readiness probe: any failure just means "not yet"
            last_error = exc
            time.sleep(0.2)
    raise AssertionError(f"the server did not become ready at {base_url}: {last_error}")


def test_demo_journey_script_completes_over_real_http() -> None:
    if not SCRIPT.is_file():
        pytest.fail(f"the journey script is missing: {SCRIPT}")

    import uvicorn

    from app.api.deps import reset_context
    from app.core.config import reset_settings_cache
    from app.main import create_app

    # Rebuild both caches from the current environment so an earlier test's
    # overridden limits (e.g. a 10-row cap) cannot make the journey load fail.
    reset_settings_cache()
    reset_context()
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True, name="splitscope-journey-server")
    thread.start()

    try:
        _wait_for_health(base_url, timeout=30)
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--base-url", base_url, "--timeout", "30"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - failure path
        pytest.fail(f"the journey script did not finish within its budget: {exc}")
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        reset_settings_cache()
        reset_context()

    output = f"{completed.stdout}\n{completed.stderr}"
    assert completed.returncode == 0, (
        f"scripts/demo_journey.py exited {completed.returncode} against {base_url}.\n{output}"
    )
    assert "EXIT 0: full live API journey passed." in output, output
    assert "failed=0" in output and "not_run=0" in output, output
    # Every journey step must have actually run, not been skipped.
    assert output.count("  PASS ") == 9, f"expected 9 passing steps:\n{output}"
