"""Voice-loop operational snapshot: facts for Cerebras, spoken analysis after."""
from __future__ import annotations

import json

from hsengine.engine import ops
from hsengine.engine.webrtc_moshi import SPOKEN_SYSTEM


def test_spoken_system_treats_casual_checkin_as_ops():
    text = SPOKEN_SYSTEM.lower()
    assert "how things are going" in text
    assert "casually" in text
    assert "special words" in text


def test_sitrep_tool_description_does_not_require_jargon():
    desc = ops.CEREBRAS_TOOLS[0]["function"]["description"].lower()
    assert "how's it going" in desc or "hows it going" in desc
    assert "even if they never say a tool name" in desc


def test_brief_activity_shortens_id():
    brief = ops._brief_activity(
        {
            "activity_id": "abcdefghijklmnop",
            "kind": "interactive_session",
            "peer": "hermes",
            "state": "running",
            "reason": "agent-rtc",
            "claims": [{"leaf": "root.internal.inference.agent-rtc", "gpu": 1}],
        }
    )
    assert brief["id"] == "ijklmnop"
    assert brief["state"] == "running"


def test_dispatch_unknown_is_json_error():
    data = json.loads(ops.dispatch("nope"))
    assert data["ok"] is False


def test_sitrep_bundles_local_peers_and_activities(monkeypatch):
    monkeypatch.setattr(
        ops,
        "hermes_local",
        lambda: {
            "project": "hermes",
            "dashboard": {"healthy": True, "detail": "http 200"},
            "moshi": True,
            "interactive": True,
            "gpus": [5],
            "workload": "interactive.agent_rtc",
        },
    )
    monkeypatch.setattr(ops, "_status_targets", lambda: ["127.0.0.1:50051"])
    monkeypatch.setattr(
        ops,
        "_peer_row",
        lambda target: {
            "target": target,
            "reachable": True,
            "project": "gaius",
            "total_gpus": 6,
            "endpoints": [
                {"capability": "thinking", "model": "Qwen", "healthy": True, "gpus": [0]}
            ],
            "surfaces": [],
        },
    )
    monkeypatch.setattr(
        ops,
        "activities",
        lambda **_k: {
            "ok": True,
            "activities": [
                {"kind": "interactive_session", "peer": "hermes", "state": "running"}
            ],
        },
    )
    snap = ops.sitrep()
    assert snap["hermes"]["interactive"] is True
    assert snap["reachable_peers"] == 1
    assert snap["peers"][0]["project"] == "gaius"
    assert snap["activities"][0]["state"] == "running"
    assert snap["activities_ok"] is True


def test_dispatch_sitrep_returns_json(monkeypatch):
    monkeypatch.setattr(ops, "sitrep", lambda: {"when": "now", "peer_count": 2})
    data = json.loads(ops.dispatch("sitrep"))
    assert data["peer_count"] == 2
