"""Interactive agent-rtc posture: Cerebras thinking, no silent local fallback."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hsengine.engine import interactive
from hsengine.engine.yk_sentinel import CEREBRAS_QUEUE, cerebras_thinking_yaml


@pytest.fixture(autouse=True)
def _reset_interactive():
    with interactive._mu:
        interactive._refcount = 0
        interactive._active = False
    yield
    with interactive._mu:
        interactive._refcount = 0
        interactive._active = False


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
        result = interactive.complete_cerebras(prompt="hi")
    assert result.text == "hello"
    assert result.peer == "cerebras"
    assert result.model == "qwen-3.8-27b"
    sent = client.post.call_args
    assert sent.args[0].endswith("/chat/completions")
    assert sent.kwargs["json"]["model"] == "qwen-3.8-27b"


def test_cerebras_thinking_yaml_is_zero_gpu_subscription():
    raw = cerebras_thinking_yaml()
    assert "yunikorn.apache.org/queue: root.external.token-metered" in raw
    assert CEREBRAS_QUEUE == "root.external.token-metered"
    assert 'federation.zndx.org/gpu: "1"' not in raw
    assert "nvidia.com/gpu" not in raw
    assert "hermes-cerebras-thinking" in raw
