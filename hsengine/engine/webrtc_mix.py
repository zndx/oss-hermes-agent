"""Outbound WebRTC audio mix: combined agent speech preempts clip soundtrack.

One audio track on the PeerConnection. Clip audio plays through the first
video pass; after that EOF the soundtrack is silenced. Agent speech always
replaces clip samples while queued. Empty / all-zero speech falls through
to whatever the clip is at that moment (first-pass audio, then silence).
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from typing import Any

log = logging.getLogger("hsengine.engine.webrtc.mix")

CANON_RATE = 48000
_MAX_SAMPLES = CANON_RATE * 30
_SPEECH_FLOOR = 1e-4  # below this, treat as silence → clip plays


class SoundtrackGate:
    """Clip soundtrack is live only until the first video loop (or audio, if no video)."""

    def __init__(self, *, has_video: bool) -> None:
        self._has_video = bool(has_video)
        self._loops = 0
        self._lock = threading.Lock()

    def on_track_eof(self, kind: str) -> None:
        if kind == "video" or (kind == "audio" and not self._has_video):
            with self._lock:
                if self._loops == 0:
                    self._loops = 1
                    log.info("clip soundtrack ended after first %s pass", kind)

    def clip_live(self) -> bool:
        with self._lock:
            return self._loops == 0


def _as_float_mono(pcm: Any) -> Any:
    import numpy as np

    arr = np.asarray(pcm)
    if arr.size == 0:
        return np.zeros(0, dtype=np.float32)
    if arr.dtype == np.int16:
        arr = arr.astype(np.float32) / 32768.0
    else:
        arr = arr.astype(np.float32)
        peak = float(np.max(np.abs(arr))) if arr.size else 0.0
        if peak > 1.5:
            arr = arr / 32768.0
    if arr.ndim == 2:
        arr = arr.mean(axis=0 if arr.shape[0] <= 8 else 1)
    return np.ascontiguousarray(arr.reshape(-1), dtype=np.float32)


def _resample_mono(pcm: Any, src_rate: int, dst_rate: int) -> Any:
    import numpy as np

    if src_rate == dst_rate or pcm.size == 0:
        return pcm
    n_out = max(1, int(round(pcm.size * dst_rate / src_rate)))
    return np.interp(
        np.linspace(0, pcm.size - 1, n_out, dtype=np.float64),
        np.arange(pcm.size, dtype=np.float64),
        pcm,
    ).astype(np.float32)


def _fit(mono: Any, n: int) -> Any:
    import numpy as np

    if mono.size == n:
        return mono
    if mono.size > n:
        return mono[:n]
    out = np.zeros(n, dtype=np.float32)
    out[: mono.size] = mono
    return out


def _to_clip_dtype(arr: Any, like: Any) -> Any:
    import numpy as np

    if like.dtype == np.int16:
        return np.clip(np.asarray(arr) * 32767.0, -32768, 32767).astype(np.int16)
    return np.asarray(arr, dtype=like.dtype)


def speech_like_clip(clip: Any, speech_mono: Any) -> Any:
    """Broadcast mono speech onto the clip frame's channel layout."""
    import numpy as np

    clip_arr = np.asarray(clip)
    if clip_arr.ndim == 1:
        return _fit(speech_mono, clip_arr.shape[0])
    if clip_arr.shape[0] <= 8:
        n = clip_arr.shape[1]
        mono = _fit(speech_mono, n)
        return np.stack([mono] * clip_arr.shape[0], axis=0)
    n = clip_arr.shape[0]
    mono = _fit(speech_mono, n)
    return np.stack([mono] * clip_arr.shape[1], axis=1)


def mix_pcm(clip: Any, speech: Any | None) -> Any:
    """Replace clip samples with speech when speech is present and audible."""
    import numpy as np

    if speech is None:
        return clip
    mono = _as_float_mono(speech)
    if mono.size == 0 or float(np.max(np.abs(mono))) < _SPEECH_FLOOR:
        return clip
    clip_arr = np.asarray(clip)
    return _to_clip_dtype(speech_like_clip(clip_arr, mono), clip_arr)


class SpeechBoard:
    """Serialized PCM from every agent source. One outbound voice later (TTS)."""

    def __init__(self, sample_rate: int = CANON_RATE) -> None:
        self.sample_rate = int(sample_rate)
        self._lock = threading.Lock()
        self._buf: deque[float] = deque()

    def push(self, pcm: Any, *, source: str = "", sample_rate: int | None = None) -> None:
        import numpy as np

        mono = _as_float_mono(pcm)
        rate = int(sample_rate or self.sample_rate)
        if rate != self.sample_rate:
            mono = _resample_mono(mono, rate, self.sample_rate)
        if mono.size == 0:
            return
        with self._lock:
            self._buf.extend(float(x) for x in mono.tolist())
            overflow = len(self._buf) - _MAX_SAMPLES
            if overflow > 0:
                for _ in range(overflow):
                    self._buf.popleft()
        log.debug("speech queued %s samples=%s source=%s", rate, mono.size, source or "-")

    def speaking(self) -> bool:
        with self._lock:
            return bool(self._buf)

    def pull(self, n: int, sample_rate: int) -> Any | None:
        """n samples at *sample_rate*, or None if no agent speech is queued."""
        import numpy as np

        if n <= 0:
            return None
        need = n if sample_rate == self.sample_rate else max(1, int(round(n * self.sample_rate / sample_rate)))
        with self._lock:
            if not self._buf:
                return None
            take = min(need, len(self._buf))
            chunk = np.fromiter((self._buf.popleft() for _ in range(take)), dtype=np.float32, count=take)
        if chunk.size < need:
            chunk = _fit(chunk, need)
        if sample_rate != self.sample_rate:
            chunk = _resample_mono(chunk, self.sample_rate, sample_rate)
            chunk = _fit(chunk, n)
        return chunk


def apply_mix_frame(frame: Any, board: SpeechBoard, gate: SoundtrackGate | None = None) -> Any:
    """Return a new audio frame with speech mixed over the clip, or the original."""
    try:
        import numpy as np
        import av
    except Exception:
        return frame
    try:
        arr = frame.to_ndarray()
        silenced = gate is not None and not gate.clip_live()
        if silenced:
            arr = np.zeros_like(arr)
        n = int(arr.shape[-1] if arr.ndim else arr.size)
        rate = int(getattr(frame, "sample_rate", 0) or CANON_RATE)
        mixed = mix_pcm(arr, board.pull(n, rate))
        # After the first video loop, arr is a zero copy — it equals mixed when
        # there is no speech, but the original frame still has clip samples.
        if not silenced and (mixed is arr or np.array_equal(mixed, arr)):
            return frame
        fmt = getattr(getattr(frame, "format", None), "name", None) or "s16"
        layout = getattr(getattr(frame, "layout", None), "name", None) or "stereo"
        out = av.AudioFrame.from_ndarray(np.asarray(mixed), format=fmt, layout=layout)
        out.pts = frame.pts
        tb = getattr(frame, "time_base", None)
        if tb is not None:
            out.time_base = tb
        out.sample_rate = rate
        return out
    except Exception:
        log.debug("audio mix failed", exc_info=True)
        return frame


def _silence_track(sample_rate: int = CANON_RATE, frame_samples: int = 960) -> Any:
    """20 ms stereo silence so speech can still go out when the clip has no audio."""
    from aiortc import MediaStreamTrack
    from aiortc.mediastreams import MediaStreamError

    class SilenceTrack(MediaStreamTrack):
        kind = "audio"

        def __init__(self) -> None:
            super().__init__()
            self._rate = sample_rate
            self._n = frame_samples
            self._pts = 0
            self._t0: float | None = None

        async def recv(self):
            if self.readyState != "live":
                raise MediaStreamError
            import av
            import numpy as np

            if self._t0 is None:
                self._t0 = time.monotonic()
            else:
                due = self._t0 + (self._pts / self._rate)
                wait = due - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
            arr = np.zeros((self._n, 2), dtype=np.int16)
            frame = av.AudioFrame.from_ndarray(arr, format="s16", layout="stereo")
            frame.sample_rate = self._rate
            frame.pts = self._pts
            self._pts += self._n
            return frame

    return SilenceTrack()


def mix_audio_track(
    clip: Any | None, board: SpeechBoard, gate: SoundtrackGate | None = None
) -> Any:
    from aiortc import MediaStreamTrack
    from aiortc.mediastreams import MediaStreamError

    inner = clip if clip is not None else _silence_track()

    class MixedAudioTrack(MediaStreamTrack):
        kind = "audio"

        def __init__(self) -> None:
            super().__init__()
            self._inner = inner

        async def recv(self):
            if self.readyState != "live":
                raise MediaStreamError
            frame = await self._inner.recv()
            return apply_mix_frame(frame, board, gate)

        def stop(self) -> None:
            try:
                self._inner.stop()
            except Exception:
                pass
            super().stop()

    return MixedAudioTrack()
