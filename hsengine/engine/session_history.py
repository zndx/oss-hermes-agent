"""AgentRTC turns in Hermes session history (the same SessionDB the dashboard lists).

One Hermes session per WebRTC Connect, source ``agent-rtc``. Persistence must
never deny a call: a store failure is logged and the voice path continues.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

log = logging.getLogger("hsengine.engine.session_history")

SOURCE = "agent-rtc"
DISPLAY_NAME = "AgentRTC"

_mu = threading.Lock()
_db: Any = None


def hermes_session_id(webrtc_id: str) -> str:
    return f"agent-rtc-{webrtc_id}"


def configure(db: Any | None) -> None:
    """Tests inject a SessionDB; production leaves this None (lazy default store)."""
    global _db
    with _mu:
        _db = db


def _store() -> Any | None:
    global _db
    with _mu:
        if _db is not None:
            return _db
        try:
            from hermes_state import SessionDB

            _db = SessionDB()
            return _db
        except Exception:
            log.warning("agent-rtc session store unavailable", exc_info=True)
            return None


def _model() -> str:
    try:
        from hsengine.config import get_str

        return get_str("hermes.engine.webrtc.interactive.cerebras_model") or "qwen-3.8-27b"
    except Exception:
        return "qwen-3.8-27b"


def open_session(webrtc_id: str, *, model: str = "") -> str | None:
    """Create the Hermes session row for this Connect. Returns the Hermes id."""
    if not webrtc_id:
        return None
    sid = hermes_session_id(webrtc_id)
    db = _store()
    if db is None:
        return None
    try:
        db.create_session(
            sid,
            SOURCE,
            model=model or _model(),
            display_name=DISPLAY_NAME,
            session_key=webrtc_id,
        )
        log.info("agent-rtc history session %s", sid)
        return sid
    except Exception:
        log.warning("agent-rtc history open failed", exc_info=True)
        return None


def record_turn(
    webrtc_id: str,
    *,
    user: str = "",
    assistant: str = "",
    model: str = "",
) -> None:
    if not webrtc_id:
        return
    sid = hermes_session_id(webrtc_id)
    user_text = (user or "").strip()
    asst_text = (assistant or "").strip()
    if not user_text and not asst_text:
        return
    db = _store()
    if db is None:
        return
    try:
        db.ensure_session(sid, SOURCE, model=model or _model(), display_name=DISPLAY_NAME)
        if user_text:
            db.append_message(sid, "user", user_text)
        if asst_text:
            db.append_message(sid, "assistant", asst_text, finish_reason="stop")
    except Exception:
        log.warning("agent-rtc history record failed", exc_info=True)


def close_session(webrtc_id: str, reason: str = "hangup") -> None:
    if not webrtc_id:
        return
    db = _store()
    if db is None:
        return
    try:
        db.end_session(hermes_session_id(webrtc_id), reason)
    except Exception:
        log.warning("agent-rtc history close failed", exc_info=True)
