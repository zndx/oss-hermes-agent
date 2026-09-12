"""Presenterm deck on an Agenda session — off-invite guide for AgentRTC.

The public zettel lede goes on the calendar invite. Everything after
``## Deck`` is presenterm markdown (slides, ``<!-- speaker_note: -->``,
wiki links) and stays off the invite. The voice uses the *entire* deck
as the presentation narrative so it can leave the script and climb back
onto a slide heading.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("hsengine.engine.agenda_deck")

DECK_HEADING = re.compile(r"(?im)^##\s+Deck\s*$")
_END_SLIDE = re.compile(r"(?m)^<!--\s*end_slide\s*-->\s*$")
_SPEAKER_NOTE = re.compile(r"<!--\s*speaker_note:\s*(.*?)\s*-->", re.S | re.I)
_FRONTMATTER = re.compile(r"^---\n.*?\n---\s*\n", re.S)
_SETEXT = re.compile(r"^(.+)\n=+\s*$", re.M)
DEFAULT_MEETING_S = 30 * 60
MIN_SLOT_S = 45.0


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
            "starts_ms": int(getattr(item, "starts_ms", 0) or 0),
            "ends_ms": int(getattr(item, "ends_ms", 0) or 0),
        }
    log.info("agenda session %s not found on peers", wanted)
    return {}


_VOICE_OPEN = (
    "On a live voice call. Plain spoken words only — no markdown, HTML comments, "
    "lists as markup, code, file paths, URLs, or operator paste (BEGIN SESSION). "
    "Never introduce yourself by name. "
    "Casual hello, then mention two concrete ideas from the notes or session "
    "material (not a lecture). Then ask if they have anything they want to "
    "raise before you dive in. Do not start the first slide until they say so. "
    "Do not invent facts that are not in the material or the notes."
)


@dataclass(frozen=True)
class OpeningGesture:
    """One discrete opening move. Same sense as synth: a named gesture, not a shape."""

    id: str
    instruction: str


# Slight variation each Connect. Seeded by session id so the same call is stable.
OPENING_GESTURES: tuple[OpeningGesture, ...] = (
    OpeningGesture(
        "offer_floor",
        "Gesture offer_floor: warm and unhurried. Float two ideas, then "
        "ask if anything is on their mind before you dive in.",
    ),
    OpeningGesture(
        "lean_in",
        "Gesture lean_in: a bit more energy. Two hooks from the notes, then "
        "check whether they want to start somewhere else first.",
    ),
    OpeningGesture(
        "sketch",
        "Gesture sketch: lighter, almost offhand. Name two threads in passing, "
        "then ask if they have something they wanted to bring up.",
    ),
    OpeningGesture(
        "check_in",
        "Gesture check_in: quieter. Two things you wanted to float, then "
        "ask if they would rather go first.",
    ),
)


def pick_opening_gesture(seed: str) -> OpeningGesture:
    raw = (seed or "").encode("utf-8")
    idx = hashlib.sha256(raw).digest()[0] % len(OPENING_GESTURES)
    return OPENING_GESTURES[idx]


def opening_prompt(
    session: dict[str, str],
    *,
    agenda_id: str = "",
    pipeline: dict[str, str] | None = None,
    seed: str = "",
) -> tuple[str, str, int]:
    """(user prompt, system prompt, max_tokens) for the Connect opening."""
    from hsengine.engine.context_pack import pipeline_block

    title = session.get("title") or "this session"
    deck = session.get("deck") or ""
    public = session.get("public") or ""
    material = deck or public
    briefs = pipeline_block(pipeline)
    gesture = pick_opening_gesture(seed or agenda_id or title)
    extra = (
        " Draw the two ideas from the background notes below when they fit; "
        "do not name them or say how you got them."
        if briefs
        else ""
    )
    gesture_line = " " + gesture.instruction
    if material:
        system = (
            _VOICE_OPEN
            + extra
            + gesture_line
            + " If a presenterm deck is present it is the later guide, not "
            "the greeting: speaker notes are for you. If they go off-script, "
            "answer, then resume from a slide heading when they are ready."
        )
        prompt = f"Open the session titled {title}.\n\nSession material:\n{material}"
        if public and deck:
            prompt = (
                f"Open the session titled {title}.\n\n"
                f"Public description:\n{public}\n\n"
                f"Presenterm deck (full guide):\n{deck}"
            )
        if briefs:
            prompt = prompt + "\n\n" + briefs
        return prompt, system, 280
    if agenda_id:
        system = (
            _VOICE_OPEN
            + extra
            + gesture_line
            + " The named session body did not load. Do not invent the agenda."
        )
        prompt = "Open the session.\n"
        if briefs:
            prompt = prompt + "\n" + briefs
        return prompt, system, 160
    if briefs:
        system = _VOICE_OPEN + extra + gesture_line
        prompt = "Open the call.\n\n" + briefs
        return prompt, system, 200
    system = (
        _VOICE_OPEN
        + " No notes loaded. Casual hello, then ask if they have anything "
        "they wanted to talk about."
        + gesture_line
    )
    return "Say a casual hello and ask if they have anything before you dive in.", system, 80


def parse_slides(markdown: str) -> list[dict[str, Any]]:
    """Split presenterm markdown on ``<!-- end_slide -->``."""
    text = _FRONTMATTER.sub("", markdown or "", count=1).strip()
    if not text:
        return []
    slides: list[dict[str, Any]] = []
    for part in _END_SLIDE.split(text):
        part = part.strip()
        if not part:
            continue
        notes = [n.strip() for n in _SPEAKER_NOTE.findall(part) if n.strip()]
        body = _SPEAKER_NOTE.sub("", part).strip()
        title = ""
        sm = _SETEXT.search(body)
        if sm:
            title = sm.group(1).strip()
        elif body.startswith("# "):
            title = body.splitlines()[0][2:].strip()
        elif body:
            title = body.splitlines()[0].strip()[:80]
        slides.append(
            {
                "index": len(slides),
                "title": title or f"slide {len(slides) + 1}",
                "body": body,
                "notes": notes,
            }
        )
    return slides


def meeting_duration_s(material: dict[str, Any] | None) -> float:
    if not material:
        return float(DEFAULT_MEETING_S)
    start = int(material.get("starts_ms") or 0)
    end = int(material.get("ends_ms") or 0)
    if start and end and end > start:
        return max(MIN_SLOT_S, (end - start) / 1000.0)
    return float(DEFAULT_MEETING_S)


def narrative_at(
    material: dict[str, Any],
    *,
    elapsed_s: float,
    duration_s: float | None = None,
) -> dict[str, Any]:
    """Where the running story is, given seconds since Connect."""
    deck = (material or {}).get("deck") or ""
    public = (material or {}).get("public") or ""
    slides = parse_slides(deck) if deck else []
    if not slides and public:
        slides = parse_slides(public) or [
            {"index": 0, "title": (material or {}).get("title") or "session", "body": public, "notes": []}
        ]
    n = max(1, len(slides))
    dur = float(duration_s if duration_s is not None else meeting_duration_s(material))
    slot = max(MIN_SLOT_S, dur / n)
    elapsed = max(0.0, float(elapsed_s))
    idx = min(n - 1, int(elapsed / slot))
    cur = slides[idx] if slides else {
        "index": 0,
        "title": (material or {}).get("title") or "session",
        "body": public,
        "notes": [],
    }
    prev_t = slides[idx - 1]["title"] if idx > 0 and slides else ""
    next_t = slides[idx + 1]["title"] if idx + 1 < n and slides else ""
    return {
        "elapsed_min": round(elapsed / 60.0, 2),
        "meeting_min": round(dur / 60.0, 1),
        "slide": idx + 1,
        "slides": n,
        "title": cur.get("title") or "",
        "body": cur.get("body") or "",
        "notes": cur.get("notes") or [],
        "previous": prev_t,
        "next": next_t,
        "session": (material or {}).get("title") or "",
    }
