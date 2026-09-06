"""WebRTC caption overlay and local STT helpers."""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from hsengine.engine.generated import hermes_engine_pb2 as pb
from hsengine.engine.server import HermesEngineServicer
from hsengine.engine.webrtc_captions import CaptionBoard, paint_caption
from hsengine.engine.webrtc_stt import frame_to_mono16k, stt_available, transcribe_pcm16k


def test_engine_status_stt_matches_faster_whisper():
    reply = asyncio.run(HermesEngineServicer().EngineStatus(pb.EngineStatusRequest(), None))
    assert ("stt" in list(reply.capabilities)) is stt_available()


def test_caption_board_holds_then_clears(monkeypatch):
    board = CaptionBoard()
    board.set("hello there")
    assert board.get() == "hello there"
    board._at = time.monotonic() - 10
    assert board.get() == ""


def test_paint_caption_changes_pixels():
    pytest.importorskip("PIL")
    from PIL import Image

    image = Image.new("RGB", (320, 180), (0, 0, 0))
    paint_caption(image, "caption overlay")
    assert image.getbbox() is not None


def test_frame_to_mono16k_downsamples_stereo():
    np = pytest.importorskip("numpy")
    frame = SimpleNamespace(
        sample_rate=48000,
        to_ndarray=lambda: np.ones((2, 4800), dtype=np.int16) * 16384,
    )
    pcm = frame_to_mono16k(frame)
    assert pcm is not None
    assert pcm.ndim == 1
    assert 1500 < pcm.size < 1800
    assert float(pcm.max()) <= 1.0


def test_transcribe_pcm16k_skips_silence():
    np = pytest.importorskip("numpy")
    quiet = np.zeros(16000, dtype=np.float32)
    assert transcribe_pcm16k(quiet) == ""


def test_transcribe_pcm16k_uses_warm_model():
    np = pytest.importorskip("numpy")
    if not stt_available():
        pytest.skip("faster-whisper extra not installed")
    segment = SimpleNamespace(text=" hello world ")
    model = MagicMock()
    model.transcribe.return_value = ([segment], None)
    speech = np.ones(16000, dtype=np.float32) * 0.2
    with patch("hsengine.engine.webrtc_stt.load_model", return_value=model):
        assert transcribe_pcm16k(speech) == "hello world"
    model.transcribe.assert_called_once()
