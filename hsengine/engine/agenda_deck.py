"""Presenterm deck on an Agenda session — off-invite guide for AgentRTC.

The public zettel lede goes on the calendar invite. Everything after
``## Deck`` is presenterm markdown (slides, ``<!-- speaker_note: -->``,
wiki links) and stays off the invite. The voice uses the *entire* deck
as the presentation narrative so it can leave the script and climb back
onto a slide heading.
"""
from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger("hsengine.engine.agenda_deck")

DECK_HEADING = re.compile(r"(?im)^##\s+Deck\s*$")


def split_public_deck(body: str) -> tuple[str, str]:
    text = body or ""
    m = DECK_HEADING.search(text)
    if not m:
        return text.strip(), ""
    return text[: m.start()].strip(), text[m.end() :].strip()


def load_agenda_session(agenda_id: str) -> dict[str, str]:
    """Fetch one Agenda item from Gaius over ServerQuery. Empty dict if missing."""
    from hsengine.engine import federation
    from hsengine.engine.generated.zndx.engine.v1 import engine_pb2 as zpb
    from hsengine.engine.ops import _status_targets

    wanted = (agenda_id or "").strip()
    if not wanted:
        return {}
    for target in _status_targets():
        resp = federation.query_peer(
            target, zpb.SERVER_QUERY_KIND_AGENDA, note_id=wanted
        )
        if resp is None:
            continue
        item = resp.agenda_hint.item
        if not (item.id or item.title or item.body):
            continue
        public, deck = split_public_deck(item.body or "")
        return {
            "id": item.id or wanted,
            "title": item.title or "",
            "public": public or item.summary or "",
            "deck": deck,
        }
    log.info("agenda session %s not found on peers", wanted)
    return {}


def opening_prompt(session: dict[str, str]) -> tuple[str, str, int]:
    """(user prompt, system prompt, max_tokens) for the Connect opening."""
    title = session.get("title") or "this session"
    deck = session.get("deck") or ""
    public = session.get("public") or ""
    if deck:
        system = (
            "You are Hermes leading an AgentRTC session. Plain spoken words only "
            "— no markdown, HTML comments, lists as markup, code, or file paths. "
            "The presenterm deck is your presentation guide and reference: slides, "
            "speaker notes, and wiki links. Lead with a short opening from the "
            "first slide (a few sentences, about a minute). Speaker notes are for "
            "you, not the audience, unless they ask to go deeper. If they go "
            "off-script, answer, then resume from a slide heading so the narrative "
            "continues. Do not invent facts that are not in the deck or tools."
        )
        prompt = (
            f"Open the session titled {title}.\n\n"
            f"Public description:\n{public}\n\n"
            f"Presenterm deck (full guide):\n{deck}"
        )
        return prompt, system, 220
    system = (
        "You are Hermes on a live voice call. One short spoken sentence only. "
        "No markdown, lists, or URLs."
    )
    return "Greet the listener in one short, clear sentence.", system, 48
