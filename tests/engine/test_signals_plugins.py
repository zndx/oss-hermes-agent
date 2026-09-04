"""Signals Hermes plugins: model-provider client, memory, compaction."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from hsengine.plugins.signals_compact import SignalsContextEngine
from hsengine.plugins.signals_memory import SignalsMemoryProvider
from hsengine.plugins.signals_oip.client import SignalsOipClient


def test_complete_fallback_maps_tool_calls():
    client = SignalsOipClient(base_url="oip://127.0.0.1:50051")
    fake = SimpleNamespace(
        text="",
        reasoning_content="think",
        finish_reason="tool_calls",
        model="Qwen",
        tool_calls=[
            SimpleNamespace(id="c1", name="terminal", arguments_json='{"command":"pwd"}'),
        ],
    )
    with patch.object(client, "_peer_has_llm_tools", return_value=False):
        with patch.object(client, "_via_complete", return_value=(
            "", "think",
            [{"id": "c1", "name": "terminal", "arguments_json": '{"command":"pwd"}'}],
            "tool_calls", "Qwen",
        )):
            resp = client.chat.completions.create(
                model="thinking",
                messages=[{"role": "user", "content": "pwd?"}],
                tools=[{"type": "function", "function": {"name": "terminal"}}],
            )
    assert resp.choices[0].finish_reason == "tool_calls"
    assert resp.choices[0].message.tool_calls[0].function.name == "terminal"
    assert "pwd" in resp.choices[0].message.tool_calls[0].function.arguments


def test_memory_sync_prefetch_and_pre_compress(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    provider = SignalsMemoryProvider()
    provider.initialize("sess-1", hermes_home=tmp_path / ".hermes")
    provider.sync_turn("prefer dark mode", "ok, noted", session_id="sess-1")
    block = provider.prefetch("dark")
    assert "dark mode" in block
    status = provider.recall_status()
    assert status is not None and status.count >= 1
    raw = json.loads(provider.handle_tool_call("signals_recall", {"query": "dark"}))
    assert raw["success"] is True
    handoff = provider.on_pre_compress([{"role": "user", "content": "keep this through compact"}])
    assert "keep this through compact" in handoff


def test_compaction_engine_name():
    engine = SignalsContextEngine(model="dummy")
    assert engine.name == "signals"
