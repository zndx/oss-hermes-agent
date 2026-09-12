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
            {
                "kind": s.get("kind"),
                "healthy": bool(s.get("healthy")),
                "url": s.get("url") or "",
            }
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
    airflow_hub = []
    for p in peers:
        for s in p.get("surfaces") or []:
            if s.get("kind") == "coordination":
                airflow_hub.append(
                    {
                        "peer": p.get("project") or p.get("target"),
                        "healthy": bool(s.get("healthy")),
                        "detail": s.get("url") or "",
                    }
                )
    return {
        "when": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "hermes": hermes_local(),
        "peers": peers,
        "activities": acts.get("activities") or [],
        "activities_ok": bool(acts.get("ok")),
        "activities_error": acts.get("error") or "",
        "airflow_hub": airflow_hub,
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


# ── agenda: today · tomorrow · the coming week, and one item on request ───────

_MAX_AGENDA_ITEMS = 16


def _brief_agenda_item(project: str, it: Any, *, with_body: bool = False) -> dict[str, Any]:
    def _when(ms: int) -> str:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%MZ") if ms else ""

    row = {
        "project": project,
        "id": it.id,
        "day": it.day or "",
        "kind": it.kind or "",
        "intent": it.intent or "",
        "title": it.title or "",
        "summary": it.summary or "",
        "starts": _when(it.starts_ms),
        "ends": _when(it.ends_ms),
        "tags": list(it.tags)[:6],
        "pinned": bool(it.pinned),
        "open_checks": int(it.open_checks or 0),
        "with": it.with_whom or "",
    }
    if with_body:
        row["body"] = it.body or ""
    return row


def agenda(*, item_id: str = "") -> dict[str, Any]:
    """The Agenda over the protocol: each peer's pre-prepared Agenda BRIEF (today ·
    tomorrow · the coming week, written by its own workflow with judgement about
    what matters) plus the index of items it covered; with `item_id`, that one
    item in full. Peers without an agenda are honest silence; unreachable ones
    are said. The peers' Agenda notes remain the deep surface."""
    from hsengine.engine import federation
    from hsengine.engine.generated.zndx.engine.v1 import engine_pb2 as zpb

    peers: list[dict[str, Any]] = []
    briefs: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    found: dict[str, Any] | None = None
    for target in _status_targets():
        resp = federation.query_peer(target, zpb.SERVER_QUERY_KIND_AGENDA, note_id=item_id or "")
        if resp is None:
            peers.append({"target": target, "reachable": False})
            continue
        h = resp.agenda_hint
        if not h.project and not h.items and not h.note and not h.brief:
            continue  # no agenda unit on this peer — honest silence
        project = h.project or resp.project
        at = datetime.fromtimestamp(int(h.brief_at_ms) / 1000, tz=timezone.utc) if h.brief_at_ms else None
        peers.append(
            {
                "target": target,
                "project": project,
                "reachable": True,
                "timezone": h.timezone or "",
                "today": h.today or "",
                "in_window": int(h.total_in_window),
                "note": h.note or "",
            }
        )
        if h.spoken or h.brief:
            briefs.append(
                {
                    "project": project,
                    "spoken": h.spoken or "",
                    "written": h.brief or "",
                    "when": at.strftime("%Y-%m-%d %H:%MZ") if at else "",
                    "age_min": int((datetime.now(timezone.utc) - at).total_seconds() // 60) if at else None,
                    "timezone": h.timezone or "",
                    "today": h.today or "",
                }
            )
        items.extend(_brief_agenda_item(project, it) for it in h.items)
        if item_id and h.item and h.item.id:
            found = _brief_agenda_item(project, h.item, with_body=True)
    out: dict[str, Any] = {
        "ok": True,
        "when": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "briefs": briefs,
        "items": items[:_MAX_AGENDA_ITEMS],
        "peers": peers,
    }
    if item_id:
        out["item_id"] = item_id
        out["item"] = found
        if found is None:
            out["item_note"] = "no peer has an agenda item with that id — read the id from a previous agenda call"
    return out


_BUFFER_STREAMS = frozenset({"hn", "fmp", "buffer"})


def search(*, query: str, stream: str = "all", limit: int = 6) -> dict[str, Any]:
    """KB and/or web hits via ServerQuery SEARCH (two hops to Gaius).

    ``stream=buffer|hn|fmp`` is the dual-cognition glance (AST upper buffer
    plus live HN/FMP entropy). Those streams allow an empty query.
    """
    from hsengine.engine import federation
    from hsengine.engine.generated.zndx.engine.v1 import engine_pb2 as zpb

    q = " ".join((query or "").split())
    kind = (stream or "all").strip().lower() or "all"
    if kind not in {"kb", "web", "all"} | _BUFFER_STREAMS:
        kind = "all"
    try:
        n = max(1, min(int(limit or 6), 8))
    except (TypeError, ValueError):
        n = 6
    if not q and kind not in _BUFFER_STREAMS:
        return {"ok": False, "error": "empty query", "hits": []}
    peers: list[dict[str, Any]] = []
    hits: list[dict[str, Any]] = []
    notes: list[str] = []
    for target in _status_targets():
        resp = federation.query_peer(
            target, zpb.SERVER_QUERY_KIND_SEARCH, query=q, stream=kind, limit=n
        )
        if resp is None:
            peers.append({"target": target, "reachable": False})
            continue
        h = resp.search_hint
        if not h.project and not h.hits and not h.note:
            continue
        peers.append({"target": target, "project": h.project or resp.project, "reachable": True})
        if h.note:
            notes.append(f"{h.project or target}: {h.note}")
        for hit in h.hits:
            hits.append(
                {
                    "title": hit.title or "",
                    "url": hit.url or "",
                    "snippet": hit.snippet or "",
                    "source": hit.source or "",
                    "score": float(hit.score or 0.0),
                    "project": h.project or resp.project,
                }
            )
    return {
        "ok": True,
        "query": q,
        "stream": kind,
        "hits": hits[: n * 2],
        "peers": peers,
        "note": "; ".join(notes),
    }


def fmp(*, query: str, stream: str = "search", limit: int = 6) -> dict[str, Any]:
    """Live FMP via ServerQuery FMP (Gaius holds the key). stream=search|news|quote."""
    from hsengine.engine import federation
    from hsengine.engine.generated.zndx.engine.v1 import engine_pb2 as zpb

    q = " ".join((query or "").split())
    kind = (stream or "search").strip().lower() or "search"
    if kind not in ("search", "news", "quote"):
        kind = "search"
    try:
        n = max(1, min(int(limit or 6), 8))
    except (TypeError, ValueError):
        n = 6
    if kind != "news" and not q:
        return {"ok": False, "error": "empty query", "hits": []}
    peers: list[dict[str, Any]] = []
    hits: list[dict[str, Any]] = []
    notes: list[str] = []
    spoken = ""
    for target in _status_targets():
        resp = federation.query_peer(
            target, zpb.SERVER_QUERY_KIND_FMP, query=q, stream=kind, limit=n
        )
        if resp is None:
            peers.append({"target": target, "reachable": False})
            continue
        h = getattr(resp, "fmp_hint", None)
        if h is None or (not h.project and not h.hits and not h.note):
            continue
        peers.append({"target": target, "project": h.project or resp.project, "reachable": True})
        if h.note:
            notes.append(f"{h.project or target}: {h.note}")
        if h.spoken and not spoken:
            spoken = h.spoken
        for hit in h.hits:
            hits.append(
                {
                    "symbol": hit.symbol or "",
                    "title": hit.title or "",
                    "snippet": hit.snippet or "",
                    "url": hit.url or "",
                    "exchange": hit.exchange or "",
                    "as_of": hit.as_of or "",
                    "source": hit.source or kind,
                    "project": h.project or resp.project,
                }
            )
    return {
        "ok": True,
        "query": q,
        "stream": kind,
        "hits": hits[: n * 2],
        "spoken": spoken,
        "peers": peers,
        "note": "; ".join(notes),
    }


def cognition_glance(*, stream: str = "buffer", limit: int = 6) -> dict[str, Any]:
    """Succinct dual-cognition buffer: AST upper buffer + HN/FMP entropy."""
    kind = (stream or "buffer").strip().lower() or "buffer"
    if kind not in _BUFFER_STREAMS:
        kind = "buffer"
    return search(query="", stream=kind, limit=limit)


def hermes(*, prompt: str) -> dict[str, Any]:
    """Run Hermes proper (full tools + subagents) on Cerebras while AgentRTC is on."""
    q = " ".join((prompt or "").split())
    if not q:
        return {"ok": False, "error": "empty prompt"}
    try:
        from agent.interactive_cerebras import overlay_runtime
        from run_agent import AIAgent
    except Exception as e:
        return {"ok": False, "error": str(e)}
    ov = overlay_runtime()
    if not ov:
        return {"ok": False, "error": "interactive AgentRTC is not in force"}
    agent = AIAgent(
        base_url=ov["base_url"],
        api_key=ov["api_key"],
        provider=ov["provider"],
        model=ov["model"],
        api_mode=ov.get("api_mode") or "chat_completions",
        quiet_mode=True,
        skip_background_review=True,
    )
    text = agent.chat(q)
    return {"ok": True, "text": text, "model": ov["model"]}


def glance_spoken(d: dict[str, Any] | None) -> str:
    """Plain-speech glance for a silence cue. Empty if the buffer was silent."""
    if not d or not d.get("ok"):
        return ""
    note = str(d.get("note") or "").strip()
    payload = note
    if ": " in note:
        prefix, rest = note.split(": ", 1)
        if prefix and " " not in prefix and rest:
            payload = rest.strip()
    if payload and "empty" not in payload.lower():
        return payload
    lines: list[str] = []
    by: dict[str, list[dict[str, Any]]] = {}
    for hit in d.get("hits") or []:
        if isinstance(hit, dict):
            by.setdefault(str(hit.get("source") or "other"), []).append(hit)
    if by.get("attention"):
        bits = [
            f"{h.get('title')}: {h.get('snippet')}"
            for h in by["attention"][:4]
            if h.get("snippet")
        ]
        if bits:
            lines.append("Attending " + "; ".join(bits))
    if by.get("hn"):
        bits = [str(h.get("title") or h.get("snippet") or "") for h in by["hn"][:4]]
        lines.append("HN: " + "; ".join(b for b in bits if b))
    if by.get("fmp"):
        bits = [str(h.get("title") or h.get("snippet") or "") for h in by["fmp"][:4]]
        lines.append("FMP: " + "; ".join(b for b in bits if b))
    return " ".join(lines)


def narrative(*, at_minute: float | None = None) -> dict[str, Any]:
    """Time-aligned presenterm place for the live AgentRTC call."""
    from hsengine.engine.webrtc_session import HUB

    return HUB.narrative_checkin(at_minute=at_minute)


def conversation(*, limit: int = 16) -> dict[str, Any]:
    """This call's recent turns plus the time-aligned narrative place."""
    from hsengine.engine import session_history
    from hsengine.engine.webrtc_session import HUB

    if not getattr(HUB, "_pcs", None):
        return {"ok": False, "error": "no live AgentRTC session"}
    sid = next(iter(HUB._pcs))
    try:
        n = max(1, min(int(limit or 16), 24))
    except (TypeError, ValueError):
        n = 16
    turns = session_history.recent_turns(sid, limit=n)
    place = HUB.narrative_checkin()
    story = {
        k: place.get(k)
        for k in (
            "elapsed_min",
            "slide",
            "slides",
            "title",
            "body",
            "notes",
            "previous",
            "next",
            "session",
            "note",
        )
        if k in place
    }
    body = str(story.get("body") or "")
    if len(body) > 1200:
        story["body"] = body[:1199].rstrip() + "…"
    return {
        "ok": True,
        "session_id": sid,
        "turns": turns,
        "count": len(turns),
        "narrative": story,
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
    {
        "type": "function",
        "function": {
            "name": "agenda",
            "description": (
                "The agenda: what is on today, what matters tomorrow and in the "
                "coming week. Returns each project's pre-prepared Agenda BRIEF "
                "(briefs[].spoken is plain speech, written by its own workflow "
                "with judgement about what to include) plus the index of the "
                "items it covered — each with an id, when, kind (session, "
                "reminder, brief) and title. Call this whenever they ask about "
                "the agenda, the schedule, meetings, reminders, what's coming up, "
                "what's planned for today or this week — casual phrasing counts. "
                "Speak the brief in your own words. When they ask about ONE item "
                "('tell me about that meeting tomorrow'), call agenda again with "
                "item_id set to that item's id from the index to get its full "
                "content. If there is no brief or the note says the agenda is "
                "empty, say so plainly."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {
                        "type": "string",
                        "description": "An item id from a previous agenda call, to read that item in full. Empty for the brief and index.",
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "conversation",
            "description": (
                "This call's own context: what we have already said, plus "
                "where the running story is at this minute. Call after a "
                "pause, interruption, or whenever you need continuity — "
                "do not guess what was said earlier. Casual phrasing counts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "How many recent turns to include (default 16).",
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "narrative",
            "description": (
                "Check in with the running session story. The pointer moves "
                "with elapsed time since Connect — at minute 4 you get the "
                "slide that belongs at minute 4, not the opening. Call this "
                "after a pause, interruption, silence cue, or whenever you "
                "have lost the thread. Then speak from that slide. Casual "
                "phrasing counts; they will not name this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "at_minute": {
                        "type": "number",
                        "description": "Override elapsed minutes (tests). Omit to use wall time since Connect.",
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kb_search",
            "description": (
                "Search the Gaius knowledge base (notes, thoughts, research) "
                "over the lattice. Use when they ask what we already know, "
                "to follow a wiki link from a presentation deck, or to look "
                "up something in our notes — even casually. Then resume the "
                "presentation from a slide heading if you were presenting."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to look up in the KB."},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the public web via Brave on the lattice. Use when they "
                "ask what's happening outside our notes, a fact you do not "
                "have, or news — even casually. Then resume the presentation "
                "from a slide heading if you were presenting. Do not invent URLs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Web search query."},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hermes",
            "description": (
                "Hermes proper: the full agent (skills, terminal, files, "
                "browser, memory, delegate_task / subagents). Use when the "
                "voice tools are not enough. Subagents also run on Cerebras "
                "while this AgentRTC session is in force. Speak the result."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "What Hermes should do.",
                    }
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fmp",
            "description": (
                "Look up markets on Financial Modeling Prep via the lattice "
                "(Gaius holds the API key). stream=search finds tickers by "
                "name, news is headlines (optional symbol), quote is a company "
                "profile. Use this instead of web_search for tickers, 10-Ks, "
                "and listed companies. Then speak from hits or spoken."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Company name or ticker. Optional for news.",
                    },
                    "stream": {
                        "type": "string",
                        "description": "search | news | quote (default search).",
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
    if name == "agenda":
        return json.dumps(agenda(item_id=str(args.get("item_id") or "")), default=str)
    if name == "conversation":
        raw = args.get("limit")
        try:
            lim = int(raw) if raw not in (None, "") else 16
        except (TypeError, ValueError):
            lim = 16
        return json.dumps(conversation(limit=lim), default=str)
    if name == "narrative":
        raw = args.get("at_minute")
        minute = None
        if raw is not None and raw != "":
            try:
                minute = float(raw)
            except (TypeError, ValueError):
                minute = None
        return json.dumps(narrative(at_minute=minute), default=str)
    if name == "kb_search":
        return json.dumps(search(query=str(args.get("query") or ""), stream="kb"), default=str)
    if name == "web_search":
        return json.dumps(search(query=str(args.get("query") or ""), stream="web"), default=str)
    if name == "fmp":
        return json.dumps(
            fmp(
                query=str(args.get("query") or ""),
                stream=str(args.get("stream") or "search"),
            ),
            default=str,
        )
    if name == "hermes":
        return json.dumps(hermes(prompt=str(args.get("prompt") or "")), default=str)
    return json.dumps({"ok": False, "error": f"unknown tool {name}"})
