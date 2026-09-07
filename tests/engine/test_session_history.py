"""AgentRTC turns land in Hermes SessionDB under source=agent-rtc."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from hermes_state import SessionDB
from hsengine.engine import session_history
from hsengine.engine.webrtc_moshi import TurnTaker


def test_open_record_close_roundtrip(tmp_path):
    db = SessionDB(db_path=tmp_path / "state.db")
    session_history.configure(db)
    try:
        sid = session_history.open_session("deadbeefcafe", model="qwen-3.8-27b")
        assert sid == "agent-rtc-deadbeefcafe"
        session_history.record_turn("deadbeefcafe", user="how's it going")
        session_history.record_turn("deadbeefcafe", assistant="Discover is the conversation today.")
        session_history.close_session("deadbeefcafe")
        row = db.get_session(sid)
        assert row["source"] == "agent-rtc"
        assert row["display_name"] == "AgentRTC"
        assert row["ended_at"]
        msgs = db.get_messages(sid)
        roles = [m["role"] for m in msgs]
        texts = [m["content"] for m in msgs]
        assert roles == ["user", "assistant"]
        assert texts[0] == "how's it going"
        assert "Discover" in texts[1]
    finally:
        session_history.configure(None)
        db.close()


def test_record_turn_does_not_raise_when_store_fails():
    session_history.configure(MagicMock())
    try:
        session_history._db.append_message.side_effect = RuntimeError("locked")
        session_history.record_turn("x", user="hello")
    finally:
        session_history.configure(None)


def test_turn_taker_writes_user_then_assistant():
    recorded: list[tuple] = []

    def _record(webrtc_id, **kwargs):
        recorded.append((webrtc_id, kwargs))

    result = MagicMock()
    result.text = "hello back"
    result.model = "qwen-3.8-27b"

    async def _run():
        taker = TurnTaker(asyncio.get_running_loop(), quiet_s=0.02, session_id="abc123")
        with patch("hsengine.engine.session_history.record_turn", _record):
            with patch("hsengine.engine.interactive.complete_cerebras", return_value=result):
                taker.on_word("hello")
                taker.on_word("there")
                await asyncio.sleep(0.08)

    asyncio.run(_run())
    assert recorded[0] == ("abc123", {"user": "hello there"})
    assert recorded[1][0] == "abc123"
    assert recorded[1][1]["assistant"] == "hello back"
