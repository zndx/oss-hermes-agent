"""Operational snapshot for the voice loop — Gaius-style sitrep, lattice facts.

Cerebras calls these tools; the spoken reply is analysis of the JSON.
Facts come from signals-protocol (Engine/Status, Scheduler/ListActivities)
and local probes. This process never talks to Kubernetes.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("hsengine.engine.ops")

_MAX_ACTIVITIES = 24


def _brief_activity(d: dict[str, Any]) -> dict[str, Any]:
    aid = str(d.get("activity_id") or "")
    reason = str(d.get("reason") or "")
    return {
        "id": aid[-8:] if len(aid) > 8 else aid,
        "kind": d.get("kind") or "",
        "peer": d.get("peer") or "",
        "state": d.get("state") or "",
        "dag": d.get("dag_id") or "",
        "owner": d.get("owner") or "",
        "reason": reason[:160],
        "claims": d.get("claims") or [],
    }


def _peer_row(target: str) -> dict[str, Any]:
    from hsengine.engine import federation

    st = federation.peer_status(target, use_cache=False)
    if not st:
        return {"target": target, "reachable": False}
    endpoints = []
    for ep in st.get("endpoints") or []:
        if not isinstance(ep, dict):
            continue
        endpoints.append(
            {
                "capability": ep.get("capability") or "",
                "model": ep.get("model") or "",
                "healthy": bool(ep.get("healthy")),
                "gpus": list(ep.get("gpu_ids") or []),
            }
        )
    return {
        "target": target,
        "reachable": True,
        "project": st.get("project") or "",
        "total_gpus": int(st.get("total_gpus") or 0),
        "endpoints": endpoints,
        "surfaces": [
            {"kind": s.get("kind"), "healthy": bool(s.get("healthy"))}
            for s in (st.get("surfaces") or [])
            if isinstance(s, dict)
        ],
    }


def _status_targets() -> list[str]:
    from hsengine.config import load_config
    from hsengine.engine import coordination, federation

    directory = ""
    try:
        directory = str(load_config().get("hermes.engine.federation.directory") or "")
    except Exception:
        directory = ""
    seen: list[str] = []
    for item in [*federation.federation_peers(), coordination.target(), directory]:
        t = str(item or "").replace("grpc://", "").strip()
        if t and t not in seen:
            seen.append(t)
    return seen


def hermes_local() -> dict[str, Any]:
    from hsengine.engine import interactive, probe
    from hsengine.engine.yk_sentinel import moshi_serving, our_gpu_ids

    dash = probe.probe_dashboard()
    return {
        "project": "hermes",
        "dashboard": {"healthy": dash.healthy, "detail": dash.detail},
        "moshi": bool(moshi_serving()),
        "interactive": bool(interactive.is_active()),
        "gpus": our_gpu_ids(),
        "workload": "interactive.agent_rtc",
    }


def activities(*, kind: str = "", active_only: bool = True) -> dict[str, Any]:
    from hsengine.engine import coordination

    try:
        rows = coordination.list_activities(
            kind=kind or "",
            active_only=bool(active_only),
            peer="",
        )
        return {
            "ok": True,
            "kind": kind or "all",
            "active_only": bool(active_only),
            "count": len(rows),
            "activities": [_brief_activity(r) for r in rows[:_MAX_ACTIVITIES]],
        }
    except Exception as e:
        log.warning("list_activities failed: %s", e)
        return {"ok": False, "error": str(e)[:240], "activities": []}


def sitrep() -> dict[str, Any]:
    """Single pane: local Hermes, federated Status, in-force activities."""
    peers = [_peer_row(t) for t in _status_targets()]
    acts = activities(kind="", active_only=True)
    return {
        "when": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "hermes": hermes_local(),
        "peers": peers,
        "activities": acts.get("activities") or [],
        "activities_ok": bool(acts.get("ok")),
        "activities_error": acts.get("error") or "",
        "reachable_peers": sum(1 for p in peers if p.get("reachable")),
        "peer_count": len(peers),
    }


CEREBRAS_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "sitrep",
            "description": (
                "How the lattice is doing right now: Hermes health, which "
                "peers answered, and what work is in force. Call this for "
                "ordinary check-ins — how's it going, what's happening, any "
                "trouble, a briefing — even if they never say a tool name."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_activities",
            "description": (
                "What work is running or queued across the federation. "
                "Use after a check-in if they want more on a project or a "
                "failed job. Casual phrasing counts; they will not name this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "description": "Activity kind, or empty for all kinds.",
                    },
                    "active_only": {
                        "type": "boolean",
                        "description": "If true, only in-force activities.",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
]


def dispatch(name: str, args: dict[str, Any] | None = None) -> str:
    args = args or {}
    if name == "sitrep":
        return json.dumps(sitrep(), default=str)
    if name == "list_activities":
        kind = str(args.get("kind") or "")
        active_only = args.get("active_only")
        if active_only is None:
            active_only = True
        return json.dumps(activities(kind=kind, active_only=bool(active_only)), default=str)
    return json.dumps({"ok": False, "error": f"unknown tool {name}"})
