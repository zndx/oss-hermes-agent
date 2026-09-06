"""High-speed local STT for inbound WebRTC audio.

Warm faster-whisper tiny.en (CUDA int8, CPU fallback). Not zndx.engine.v1
and not the CLI voice path — this is the caption overlay feed.
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import threading
from typing import Any

log = logging.getLogger("hsengine.engine.webrtc.stt")

_RATE = 16000
_RMS_MIN = 0.012
_model: Any = None
_model_lock = threading.Lock()


def stt_available() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


def _cfg_str(path: str, default: str) -> str:
    try:
        from hsengine.config import get_str

        value = get_str(path)
        return value if value else default
    except Exception:
        return default


def _cfg_int(path: str, default: int) -> int:
    try:
        from hsengine.config import get_int

        return int(get_int(path))
    except Exception:
        return default


def load_model() -> Any:
    global _model
    if _model is not None:
        return _model
    if not stt_available():
        raise RuntimeError("faster-whisper is not installed (hermes-agent[engine])")
    from faster_whisper import WhisperModel

    name = _cfg_str("hermes.engine.webrtc.stt.model", "tiny.en")
    with _model_lock:
        if _model is not None:
            return _model
        try:
            _model = WhisperModel(name, device="cuda", compute_type="int8")
            log.info("webrtc stt model=%s device=cuda", name)
        except Exception as exc:
            log.warning("webrtc stt CUDA unavailable (%s) — CPU int8", exc)
            _model = WhisperModel(name, device="cpu", compute_type="int8")
            log.info("webrtc stt model=%s device=cpu", name)
    return _model


def frame_to_mono16k(frame: Any) -> Any:
    """Return float32 mono PCM at 16 kHz, or None."""
    import numpy as np

    try:
        arr = frame.to_ndarray()
    except Exception:
        return None
    arr = np.asarray(arr)
    if arr.size == 0:
        return None
    if arr.dtype == np.int16:
        pcm = arr.astype(np.float32) / 32768.0
    else:
        pcm = arr.astype(np.float32)
        peak = float(np.max(np.abs(pcm))) if pcm.size else 0.0
        if peak > 1.5:
            pcm = pcm / 32768.0
    if pcm.ndim == 2:
        pcm = pcm.mean(axis=0 if pcm.shape[0] <= 8 else 1)
    src_rate = int(getattr(frame, "sample_rate", 0) or _RATE)
    if src_rate != _RATE and pcm.size:
        n_out = max(1, int(round(pcm.size * _RATE / src_rate)))
        pcm = np.interp(
            np.linspace(0, pcm.size - 1, n_out, dtype=np.float64),
            np.arange(pcm.size, dtype=np.float64),
            pcm,
        ).astype(np.float32)
    return pcm


def transcribe_pcm16k(samples: Any) -> str:
    import numpy as np

    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    if audio.size < _RATE // 10:
        return ""
    rms = float(np.sqrt(np.mean(np.square(audio))))
    if rms < _RMS_MIN:
        return ""
    model = load_model()
    language = _cfg_str("hermes.engine.webrtc.stt.language", "en")
    segments, _info = model.transcribe(
        audio,
        language=language or None,
        beam_size=1,
        vad_filter=True,
        condition_on_previous_text=False,
        without_timestamps=True,
    )
    parts = []
    for segment in segments:
        text = (getattr(segment, "text", "") or "").strip()
        if text:
            parts.append(text)
    return " ".join(parts).strip()


async def follow_audio(track: Any, board: Any) -> None:
    """Pull inbound WebRTC audio and push caption text onto *board*."""
    import numpy as np

    window = max(200, _cfg_int("hermes.engine.webrtc.stt.window_ms", 800))
    hop = max(100, _cfg_int("hermes.engine.webrtc.stt.hop_ms", 400))
    need = int(_RATE * window / 1000)
    hop_n = int(_RATE * hop / 1000)
    buf: list[Any] = []
    busy = False

    async def _emit(chunk: Any) -> None:
        nonlocal busy
        try:
            text = await asyncio.to_thread(transcribe_pcm16k, chunk)
            if text:
                board.set(text)
        except Exception:
            log.debug("webrtc stt chunk failed", exc_info=True)
        finally:
            busy = False

    try:
        while True:
            frame = await track.recv()
            pcm = frame_to_mono16k(frame)
            if pcm is None or pcm.size == 0:
                continue
            buf.append(pcm)
            audio = np.concatenate(buf)
            if audio.size < need:
                buf = [audio]
                continue
            take = audio[-need:]
            buf = [audio[hop_n:]] if hop_n < audio.size else []
            if busy:
                continue
            busy = True
            asyncio.create_task(_emit(take))
    except asyncio.CancelledError:
        raise
    except Exception:
        log.info("webrtc stt follow ended")
