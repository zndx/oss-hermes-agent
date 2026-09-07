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


# ── recent_thoughts: "what have you been thinking about?" over the protocol ──

def peers_have_brief(out):
    return any(p.get("brief", {}).get("written") for p in out["peers"])


def test_recent_thoughts_merges_peer_hints_newest_first(monkeypatch):
    import time
    from concurrent import futures

    import grpc

    from hsengine.engine import ops
    from hsengine.engine.generated.zndx.engine.v1 import engine_pb2 as zpb
    from hsengine.engine.generated.zndx.engine.v1 import engine_pb2_grpc as zpb_grpc

    now_ms_ref = [int(time.time() * 1000)]

    class FakeEngine(zpb_grpc.EngineServicer):
        def __init__(self, project, thoughts, note=""):
            self.project, self.thoughts, self.note = project, thoughts, note
            self.requests = []

        def ServerQuery(self, request, context):  # noqa: N802
            self.requests.append(request)
            resp = zpb.ServerQueryResponse(project=self.project)
            if request.kind == zpb.SERVER_QUERY_KIND_THOUGHTS and (self.thoughts or self.note):
                # a peer WITHOUT a cognition unit leaves the hint unset (honest silence)
                h = resp.thoughts_hint
                h.project = self.project
                h.note = self.note
                h.total_in_window = len(self.thoughts)
                for i, (title, at_ms) in enumerate(self.thoughts):
                    h.thoughts.append(zpb.Thought(id=f"t{i}", at_ms=at_ms, kind="connection", title=title,
                                                  summary=f"{title} — summary", domains=["biorxiv"], salience=0.5))
                if self.thoughts:
                    h.newest_ms = max(a for _, a in self.thoughts)
                if getattr(self, 'brief', ''):
                    h.brief = self.brief
                    h.spoken = self.brief + ' (spoken)'
                    h.brief_at_ms = now_ms_ref[0] - 120_000
                    h.brief_thoughts = 7
            return resp

    now_ms = now_ms_ref[0]
    gaius = FakeEngine("gaius", [("older", now_ms - 3_600_000), ("newest", now_ms - 60_000)])
    gaius.brief = "Lately I have been thinking about state as a control plane."
    silent = FakeEngine("aegir", [])  # no cognition unit: empty hint → honest silence
    servers, targets = [], []
    for fake in (gaius, silent):
        srv = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
        zpb_grpc.add_EngineServicer_to_server(fake, srv)
        port = srv.add_insecure_port("127.0.0.1:0"); srv.start()
        servers.append(srv); targets.append(f"127.0.0.1:{port}")
    targets.append("127.0.0.1:1")  # unreachable peer
    monkeypatch.setattr(ops, "_status_targets", lambda: targets)
    try:
        out = ops.recent_thoughts(limit=5, since_hours=6, kind="connection")
    finally:
        for srv in servers:
            srv.stop(0)
    assert out["ok"] and out["count"] == 2
    assert out["briefs"][0]["project"] == "gaius" and out["briefs"][0]["spoken"].endswith("(spoken)")
    assert out["briefs"][0]["thoughts_considered"] == 7 and 1 <= out["briefs"][0]["age_min"] <= 3
    assert peers_have_brief(out)
    assert [t["title"] for t in out["thoughts"]] == ["newest", "older"]
    assert out["thoughts"][0]["project"] == "gaius" and out["thoughts"][0]["kind"] == "connection"
    peers = {p.get("target"): p for p in out["peers"]}
    assert peers[targets[0]]["reachable"] and peers[targets[0]]["in_window"] == 2
    assert targets[1] not in peers  # silent peer omitted
    assert peers["127.0.0.1:1"]["reachable"] is False
    req = gaius.requests[0]
    assert req.kind == zpb.SERVER_QUERY_KIND_THOUGHTS and req.limit == 5 and req.stream == "connection"
    assert req.since_ms > now_ms - 7 * 3_600_000 and req.origin_project == "hermes"
    # the tool is dispatchable and declared to Cerebras
    assert "recent_thoughts" in [t["function"]["name"] for t in ops.CEREBRAS_TOOLS]
    import json
    assert json.loads(ops.dispatch("recent_thoughts", {"limit": "2"}))["ok"] is True
