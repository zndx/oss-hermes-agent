"""Interactive agent-rtc posture: Cerebras thinking, no silent local fallback."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hsengine.engine import interactive


@pytest.fixture(autouse=True)
def _reset_interactive():
    with interactive._mu:
        interactive._refcount = 0
        interactive._active = False
        interactive._lease = None
    yield
    with interactive._mu:
        interactive._refcount = 0
        interactive._active = False
        interactive._lease = None


def test_enter_requires_cerebras_key(monkeypatch):
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="CEREBRAS_API_KEY"):
        interactive.enter()
    assert interactive.is_active() is False


def test_complete_cerebras_posts_qwen38(monkeypatch):
    monkeypatch.setenv("CEREBRAS_API_KEY", "test-key")
    payload = {
        "model": "qwen-3.8-27b",
        "choices": [{"message": {"content": "hello", "reasoning": ""}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1},
    }
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status = MagicMock()
    client = MagicMock()
    client.post.return_value = response
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    with patch("hsengine.engine.interactive.httpx.Client", return_value=client):
        with patch("hsengine.engine.interactive._speak_cerebras"):
            result = interactive.complete_cerebras(prompt="hi")
    assert result.text == "hello"
    assert result.peer == "cerebras"
    assert result.model == "qwen-3.8-27b"
    sent = client.post.call_args
    assert sent.args[0].endswith("/chat/completions")
    assert sent.kwargs["json"]["model"] == "qwen-3.8-27b"


def test_require_declared_workload_denies_missing_claims():
    with pytest.raises(RuntimeError, match="did not echo the agent-rtc workload claims"):
        interactive._require_declared_workload({"state": "running", "claims": []})


def test_require_declared_workload_denies_activity_not_in_force():
    claims = [{"leaf": "root.internal.inference.agent-rtc", "gpu": 1}]
    with pytest.raises(RuntimeError, match="not in force"):
        interactive._require_declared_workload({"state": "failed", "claims": claims})


def test_require_declared_workload_denies_external_local_gpu():
    claims = [
        {"leaf": "root.internal.inference.agent-rtc", "gpu": 1},
        {"leaf": "root.external.token-metered", "gpu": 1},
    ]
    with pytest.raises(RuntimeError, match="must not claim local GPUs"):
        interactive._require_declared_workload({"state": "running", "claims": claims})
