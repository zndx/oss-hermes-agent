"""Fresh cognition / thoughts / agenda briefs for an AgentRTC opening.

The Airflow-initiated Gaius pipelines (cognition_cycle → thoughts brief,
agenda_brief after producers, article_curate) already write these. Connect
loads the spoken forms so Cerebras starts from today's pipeline, not a
blank greeting. Failures are empty — never invent a brief.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("hsengine.engine.context_pack")

_SPOKEN_CAP = 800


def _clip(text: str, n: int = _SPOKEN_CAP) -> str:
    t = " ".join((text or "").split())
    if len(t) <= n:
        return t
    cut = t[: n - 1].rsplit(" ", 1)[0]
    return cut + "…"


def conversational_context(*, agenda_id: str = "") -> dict[str, str]:
    """Spoken agenda + thoughts briefs (and the named item, if any)."""
    from hsengine.engine import ops

    out: dict[str, str] = {}
    try:
        agenda = ops.agenda(item_id=agenda_id or "")
    except Exception:
        log.warning("agenda brief fetch failed", exc_info=True)
        agenda = {}
    briefs = agenda.get("briefs") if isinstance(agenda, dict) else None
    if isinstance(briefs, list) and briefs:
        spoken = str(briefs[0].get("spoken") or briefs[0].get("written") or "")
        if spoken:
            out["agenda_spoken"] = _clip(spoken)
    if agenda_id and isinstance(agenda, dict):
        item = agenda.get("item") if isinstance(agenda.get("item"), dict) else None
        if item:
            body = str(item.get("body") or item.get("summary") or "")
            title = str(item.get("title") or "")
            if title:
                out["agenda_title"] = title
            if body:
                out["agenda_item"] = _clip(body, 1200)
    try:
        thoughts = ops.recent_thoughts(limit=4, since_hours=24)
    except Exception:
        log.warning("thoughts brief fetch failed", exc_info=True)
        thoughts = {}
    tbriefs = thoughts.get("briefs") if isinstance(thoughts, dict) else None
    if isinstance(tbriefs, list) and tbriefs:
        spoken = str(tbriefs[0].get("spoken") or tbriefs[0].get("written") or "")
        if spoken:
            out["thoughts_spoken"] = _clip(spoken)
    return out


def pipeline_block(pack: dict[str, str] | None) -> str:
    """Plain-text block to splice into the opening prompt."""
    if not pack:
        return ""
    parts: list[str] = []
    agenda = pack.get("agenda_spoken") or ""
    if agenda:
        parts.append("Today's agenda brief:\n" + agenda)
    thoughts = pack.get("thoughts_spoken") or ""
    if thoughts:
        parts.append("Latest thoughts brief:\n" + thoughts)
    return "\n\n".join(parts)
