"""Interactive agent-rtc posture: Cerebras thinking, no silent local fallback."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hsengine.engine import interactive


def test_spoken_text_strips_markdown_and_urls():
    assert interactive.spoken_text("Hello **there** from https://x.ai now") == "Hello there from now"
    assert interactive.spoken_text("```code``` hi") == "hi"


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


def _client_with_payloads(payloads: list[dict]) -> MagicMock:
    leftover = list(payloads)

    def _post(*_a, **_k):
        response = MagicMock()
        response.json.return_value = leftover.pop(0)
        response.raise_for_status = MagicMock()
        return response

    client = MagicMock()
    client.post.side_effect = _post
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    return client


def test_complete_cerebras_posts_qwen38(monkeypatch):
    monkeypatch.setenv("CEREBRAS_API_KEY", "test-key")
    payload = {
        "model": "qwen-3.8-27b",
        "choices": [{"message": {"content": "hello", "reasoning": ""}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1},
    }
    client = _client_with_payloads([payload])
    with patch("hsengine.engine.interactive.httpx.Client", return_value=client):
        with patch("hsengine.engine.interactive._speak_cerebras"):
            result = interactive.complete_cerebras(prompt="hi", tools=False)
    assert result.text == "hello"
    assert result.peer == "cerebras"
    assert result.model == "qwen-3.8-27b"
    sent = client.post.call_args
    assert sent.args[0].endswith("/chat/completions")
    assert sent.kwargs["json"]["model"] == "qwen-3.8-27b"
    assert "tools" not in sent.kwargs["json"]


def test_complete_cerebras_checkin_runs_sitrep_then_speaks(monkeypatch):
    monkeypatch.setenv("CEREBRAS_API_KEY", "test-key")
    first = {
        "model": "qwen-3.8-27b",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "sitrep", "arguments": "{}"},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {},
    }
    second = {
        "model": "qwen-3.8-27b",
        "choices": [
            {
                "message": {
                    "content": "Gaius is up and this session is running.",
                    "reasoning": "",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {},
    }
    client = _client_with_payloads([first, second])
    with patch("hsengine.engine.interactive.httpx.Client", return_value=client):
        with patch("hsengine.engine.ops.dispatch", return_value='{"reachable_peers": 2}'):
            with patch("hsengine.engine.interactive._speak_cerebras"):
                result = interactive.complete_cerebras(
                    prompt="how's it going",
                    tools=True,
                )
    assert result.text == "Gaius is up and this session is running."
    assert client.post.call_count == 2
    follow = client.post.call_args_list[1].kwargs["json"]["messages"]
    assert any(m.get("role") == "tool" for m in follow)


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


def test_require_declared_workload_allows_token_metered_and_compute_at_gpu_zero():
    claims = [
        {"leaf": "root.internal.inference.agent-rtc", "gpu": 1},
        {"leaf": "root.external.token-metered", "gpu": 0},
        {"leaf": "root.internal.compute", "gpu": 0},
    ]
    interactive._require_declared_workload({"state": "running", "claims": claims})
