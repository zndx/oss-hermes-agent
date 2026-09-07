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


_MAX_THOUGHTS = 8


def _brief_thought(project: str, t: Any) -> dict[str, Any]:
    at = datetime.fromtimestamp(int(t.at_ms) / 1000, tz=timezone.utc) if t.at_ms else None
    return {
        "project": project,
        "when": at.strftime("%Y-%m-%d %H:%MZ") if at else "",
        "kind": t.kind or "",
        "title": t.title or "",
        "summary": t.summary or t.excerpt or "",
        "domains": list(t.domains)[:6],
        "salience": round(float(t.salience or 0.0), 2),
        "chain": (t.chain_id or "")[-8:],
        "generation": int(t.generation or 0),
    }


def recent_thoughts(*, limit: int = 6, since_hours: int = 24, kind: str = "") -> dict[str, Any]:
    """What the federation's cognition has been thinking about — the newest
    persisted thoughts of every peer that serves ServerQuery kind=THOUGHTS
    (gaius today), newest first, with each peer's own honest note (idle, empty,
    unreachable). Content, not counts; the peers' KBs stay the deep surface."""
    from hsengine.engine import federation
    from hsengine.engine.generated.zndx.engine.v1 import engine_pb2 as zpb

    n = max(1, min(int(limit or 6), _MAX_THOUGHTS))
    hours = max(1, int(since_hours or 24))
    since_ms = int((datetime.now(timezone.utc).timestamp() - hours * 3600) * 1000)
    peers: list[dict[str, Any]] = []
    thoughts: list[dict[str, Any]] = []
    briefs: list[dict[str, Any]] = []
    for target in _status_targets():
        resp = federation.query_peer(
            target, zpb.SERVER_QUERY_KIND_THOUGHTS, limit=n, since_ms=since_ms, stream=kind or ""
        )
        if resp is None:
            peers.append({"target": target, "reachable": False})
            continue
        h = resp.thoughts_hint
        if not h.project and not h.thoughts and not h.note:
            continue  # this peer has no cognition unit — honest silence, not an error
        newest = (
            datetime.fromtimestamp(int(h.newest_ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%MZ")
            if h.newest_ms
            else ""
        )
        row = {
            "target": target,
            "project": h.project or resp.project,
            "reachable": True,
            "in_window": int(h.total_in_window),
            "cycles": int(h.cycles_in_window),
            "newest": newest,
            "note": h.note or "",
        }
        # The peer's own Thoughts BRIEF (written by its cognition cycle in the
        # Agenda framing): the ready answer. `spoken` is the voice form.
        if h.spoken or h.brief:
            at = datetime.fromtimestamp(int(h.brief_at_ms) / 1000, tz=timezone.utc) if h.brief_at_ms else None
            row["brief"] = {
                "spoken": h.spoken or "",
                "written": h.brief or "",
                "when": at.strftime("%Y-%m-%d %H:%MZ") if at else "",
                "age_min": int((datetime.now(timezone.utc) - at).total_seconds() // 60) if at else None,
                "thoughts_considered": int(h.brief_thoughts),
            }
            briefs.append({"project": row["project"], **row["brief"]})
        peers.append(row)
        thoughts.extend(_brief_thought(h.project or resp.project, t) for t in h.thoughts)
    thoughts.sort(key=lambda t: t.get("when") or "", reverse=True)
    return {
        "ok": True,
        "when": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "window_hours": hours,
        "kind": kind or "all",
        "briefs": briefs,
        "count": len(thoughts[:n]),
        "thoughts": thoughts[:n],
        "peers": peers,
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
    {
        "type": "function",
        "function": {
            "name": "recent_thoughts",
            "description": (
                "What you have been thinking about lately. Returns each peer's "
                "Thoughts BRIEF — a short first-person summary its cognition wrote "
                "at the end of its last cycle (briefs[].spoken is already in plain "
                "speech) — plus the newest individual thoughts (patterns, "
                "connections, questions) with when each was thought. Call this "
                "whenever they ask what's on your mind, what you've been thinking, "
                "any new ideas, insights or connections, or what the research has "
                "turned up — casual phrasing counts. Speak the brief in your own "
                "words first; use the individual thoughts only for follow-ups. If "
                "there is no brief or the note says cognition is idle, say that "
                "plainly."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "How many thoughts, 1–8 (default 6)."},
                    "since_hours": {"type": "integer", "description": "Look back this many hours (default 24)."},
                    "kind": {
                        "type": "string",
                        "description": "pattern | connection | question | reflection | audit, or empty for all.",
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
    if name == "recent_thoughts":
        try:
            limit = int(args.get("limit") or 6)
        except (TypeError, ValueError):
            limit = 6
        try:
            since_hours = int(args.get("since_hours") or 24)
        except (TypeError, ValueError):
            since_hours = 24
        return json.dumps(
            recent_thoughts(limit=limit, since_hours=since_hours, kind=str(args.get("kind") or "")),
            default=str,
        )
    return json.dumps({"ok": False, "error": f"unknown tool {name}"})
