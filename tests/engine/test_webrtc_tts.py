"""Kyutai TTS client: Cerebras text → SpeechBoard PCM."""
from __future__ import annotations

import numpy as np

from hsengine.engine.webrtc_mix import SpeechBoard
from hsengine.engine.webrtc_tts import speak_into, tts_url, tts_voice


def test_tts_url_is_the_moshi_streaming_path():
    assert tts_url().endswith("/api/tts_streaming")
    assert tts_voice()


def test_speak_into_preempts_clip_on_the_board(monkeypatch):
    pcm = np.ones(4800, dtype=np.float32) * 0.4

    async def _synth(text: str):
        assert "hello" in text.lower()
        return pcm

    monkeypatch.setattr("hsengine.engine.webrtc_tts.synthesize", _synth)
    board = SpeechBoard()
    speak_into(board, "hello from cerebras", source="cerebras")
    assert board.speaking() is True
    got = board.pull(4800, 48000)
    assert got is not None
    assert float(np.max(np.abs(got))) > 0
