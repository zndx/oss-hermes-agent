"""Kyutai TTS (moshi-server /api/tts_streaming) → SpeechBoard PCM.

Cerebras return text is spoken in one voice on the WebRTC audio track.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlencode, urlparse

log = logging.getLogger("hsengine.engine.webrtc.tts")

TTS_RATE = 24000


def _cfg_str(path: str, default: str) -> str:
    try:
        from hsengine.config import get_str

        value = get_str(path)
        return value if value else default
    except Exception:
        return default


def tts_url() -> str:
    return _cfg_str(
        "hermes.engine.webrtc.tts.moshi_url",
        "ws://127.0.0.1:5080/api/tts_streaming",
    )


def tts_key() -> str:
    return _cfg_str("hermes.engine.webrtc.tts.moshi_key", "public_token")


def tts_voice() -> str:
    return _cfg_str(
        "hermes.engine.webrtc.tts.voice",
        "unmute-prod-website/p329_022.wav",
    )


def tts_host_port() -> tuple[str, int]:
    parsed = urlparse(tts_url())
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5080
    return host, port


async def synthesize(text: str) -> Any:
    """Stream Kyutai TTS; return float32 mono PCM at 24 kHz, or empty array."""
    import msgpack
    import numpy as np
    import websockets

    cleaned = " ".join((text or "").split())
    if not cleaned:
        return np.zeros(0, dtype=np.float32)
    params = {"voice": tts_voice(), "format": "PcmMessagePack"}
    uri = f"{tts_url()}?{urlencode(params)}"
    headers = {"kyutai-api-key": tts_key()}
    chunks: list[Any] = []
    async with websockets.connect(
        uri, additional_headers=headers, open_timeout=10, max_size=2**24
    ) as ws:
        for word in cleaned.split():
            await ws.send(msgpack.packb({"type": "Text", "text": word}, use_bin_type=True))
        await ws.send(msgpack.packb({"type": "Eos"}, use_bin_type=True))
        async for raw in ws:
            data = msgpack.unpackb(raw, raw=False)
            if not isinstance(data, dict):
                continue
            if data.get("type") == "Audio":
                pcm = np.asarray(data.get("pcm") or [], dtype=np.float32).reshape(-1)
                if pcm.size:
                    chunks.append(pcm)
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks)


def speak_into(board: Any, text: str, *, source: str = "cerebras") -> None:
    """Block until TTS finishes, then queue PCM on *board* (preempts clip audio)."""
    pcm = asyncio.run(synthesize(text))
    if getattr(pcm, "size", 0) == 0:
        raise RuntimeError("Kyutai TTS returned no audio")
    board.push(pcm, source=source, sample_rate=TTS_RATE)
    log.info("queued %s samples from %s (%s chars)", pcm.size, source, len(text or ""))


def speak_on_session_boards(text: str, *, source: str = "cerebras") -> None:
    from hsengine.engine.webrtc_session import HUB

    boards = [b for b in getattr(HUB, "_speech", {}).values() if b is not None]
    if not boards:
        return
    pcm = asyncio.run(synthesize(text))
    if getattr(pcm, "size", 0) == 0:
        raise RuntimeError("Kyutai TTS returned no audio")
    for board in boards:
        board.push(pcm, source=source, sample_rate=TTS_RATE)
    log.info("spoke %s onto %s board(s)", source, len(boards))
