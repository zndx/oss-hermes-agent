"""Live interactive posture: Cerebras thinking + YK token-metered stamp.

Skipped unless kubectl, CEREBRAS_API_KEY, and the moshi supervisor are up.
Does not print secrets.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

from hsengine.engine import interactive
from hsengine.engine.yk_sentinel import CEREBRAS_QUEUE, CEREBRAS_WORKLOAD_ID, QUEUE, WORKLOAD_ID

# conftest strips *_API_KEY before each test. Snapshot at import.
_KEY_SNAP = os.environ.get("CEREBRAS_API_KEY") or ""


def _ensure_key() -> bool:
    if _KEY_SNAP:
        os.environ["CEREBRAS_API_KEY"] = _KEY_SNAP
        return True
    try:
        interactive._cerebras_key()
        return True
    except RuntimeError:
        return False


def _supervisor_up() -> bool:
    try:
        s = socket.create_connection(("127.0.0.1", 5081), 1)
        s.close()
        return True
    except OSError:
        return False


def _kubectl(*args: str) -> str:
    env = os.environ.copy()
    env["KUBECONFIG"] = str(Path.home() / ".config/kube/rke2.yaml")
    r = subprocess.run(
        ["kubectl", *args],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        check=False,
    )
    return (r.stdout or "") + (r.stderr or "")


@pytest.mark.integration
def test_cerebras_thinking_token_metered_and_qwen38_complete():
    if shutil.which("kubectl") is None:
        pytest.skip("kubectl not on PATH")
    if not _ensure_key():
        pytest.skip("CEREBRAS_API_KEY not configured")

    from hsengine.engine.yk_sentinel import apply_cerebras_thinking, delete_sentinel, wait_admitted

    apply_cerebras_thinking()
    try:
        wait_admitted(CEREBRAS_WORKLOAD_ID, timeout_s=60)
        cerebras = _kubectl(
            "-n",
            "federation-signals",
            "get",
            "pod",
            CEREBRAS_WORKLOAD_ID,
            "-o",
            "jsonpath={.status.phase},{.metadata.annotations.yunikorn\\.apache\\.org/queue}",
        )
        assert "Running" in cerebras
        assert CEREBRAS_QUEUE in cerebras
        result = interactive.complete_cerebras(
            prompt="Reply with the single word: pong",
            max_tokens=32,
            temperature=0,
            reasoning_effort="none",
        )
        assert result.peer == "cerebras"
        assert result.model == "qwen-3.8-27b"
        assert "pong" in result.text.lower()
    finally:
        delete_sentinel(CEREBRAS_WORKLOAD_ID)


@pytest.mark.integration
def test_interactive_profile_stamps_cerebras_thinking_and_completes():
    if shutil.which("kubectl") is None:
        pytest.skip("kubectl not on PATH")
    if not _ensure_key():
        pytest.skip("CEREBRAS_API_KEY not configured")
    if not _supervisor_up():
        pytest.skip("moshi supervisor :5081 not up")

    with interactive._mu:
        interactive._refcount = 0
        interactive._active = False

    interactive.enter()
    try:
        assert interactive.is_active()
        cerebras = _kubectl(
            "-n",
            "federation-signals",
            "get",
            "pod",
            CEREBRAS_WORKLOAD_ID,
            "-o",
            "jsonpath={.status.phase},{.metadata.annotations.yunikorn\\.apache\\.org/queue}",
        )
        assert "Running" in cerebras
        assert CEREBRAS_QUEUE in cerebras
        rtc = _kubectl(
            "-n",
            "federation-signals",
            "get",
            "pod",
            WORKLOAD_ID,
            "-o",
            "jsonpath={.status.phase},{.metadata.annotations.yunikorn\\.apache\\.org/queue}",
        )
        assert "Running" in rtc
        assert QUEUE in rtc
        result = interactive.complete_cerebras(
            prompt="Reply with the single word: pong",
            max_tokens=16,
            temperature=0,
        )
        assert result.peer == "cerebras"
        assert "qwen" in result.model.lower() or result.model == "qwen-3.8-27b"
        assert result.text
        assert "pong" in result.text.lower()
    finally:
        interactive.leave()

    assert interactive.is_active() is False
    gone = _kubectl(
        "-n",
        "federation-signals",
        "get",
        "pod",
        CEREBRAS_WORKLOAD_ID,
        "--ignore-not-found=true",
    )
    assert CEREBRAS_WORKLOAD_ID not in gone or "Terminating" in gone or gone.strip() == ""
