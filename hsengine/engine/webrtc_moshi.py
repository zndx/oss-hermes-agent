"""Kyutai STT over moshi-server (Candle) for WebRTC captions.

Same Rust server Unmute uses. Streams 24 kHz PCM, receives Word events.
Moshi 7B dialogue is a different module: its text stream is the assistant
inner monologue, not a transcript of the user.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

log = logging.getLogger("hsengine.engine.webrtc.moshi")

_MOSHI_RATE = 24000
_CHUNK = 1920  # 80 ms at 24 kHz


def _cfg_str(path: str, default: str) -> str:
    try:
        from hsengine.config import get_str

        value = get_str(path)
        return value if value else default
    except Exception:
        return default


def moshi_url() -> str:
    return _cfg_str(
        "hermes.engine.webrtc.stt.moshi_url",
        "ws://127.0.0.1:5080/api/asr-streaming",
    )


def moshi_key() -> str:
    return _cfg_str("hermes.engine.webrtc.stt.moshi_key", "public_token")


def moshi_host_port() -> tuple[str, int]:
    parsed = urlparse(moshi_url())
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    if parsed.scheme == "ws" and parsed.port is None:
        port = 5080
    return host, port


class MoshiCaptioner:
    """Accumulate streaming Word events into a caption line."""

    def __init__(self, board: Any, max_words: int = 16) -> None:
        self.board = board
        self.max_words = max_words
        self.words: list[str] = []

    def on_message(self, data: dict) -> str | None:
        kind = data.get("type")
        if kind == "Word":
            word = str(data.get("text") or "").strip()
            if not word:
                return None
            self.words.append(word)
            del self.words[: -self.max_words]
            line = " ".join(self.words)
            self.board.set(line)
            log.info("stt word %r line=%r", word, line)
            return line
        if kind == "Step":
            return None
        return None


def frame_to_mono24k(frame: Any) -> Any:
    from hsengine.engine.webrtc_stt import frame_to_mono

    return frame_to_mono(frame, rate=_MOSHI_RATE)


async def follow_audio(track: Any, board: Any) -> None:
    """Drain inbound WebRTC audio into moshi-server ASR."""
    import msgpack
    import numpy as np
    import websockets

    captioner = MoshiCaptioner(board)
    url = moshi_url()
    if "auth_id=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}auth_id={moshi_key()}"
    headers = {"kyutai-api-key": moshi_key()}
    chunks: asyncio.Queue[Any] = asyncio.Queue(maxsize=48)

    async def ingest() -> None:
        pending = np.zeros((0,), dtype=np.float32)
        try:
            while True:
                frame = await track.recv()
                pcm = frame_to_mono24k(frame)
                if pcm is None or getattr(pcm, "size", 0) == 0:
                    continue
                pending = np.concatenate([pending, np.asarray(pcm, dtype=np.float32).reshape(-1)])
                while pending.size >= _CHUNK:
                    piece = pending[:_CHUNK]
                    pending = pending[_CHUNK:]
                    if chunks.full():
                        try:
                            chunks.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    await chunks.put(piece)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.info("moshi stt ingest ended")

    async def pump() -> None:
        while True:
            try:
                async with websockets.connect(
                    url, additional_headers=headers, open_timeout=5, max_size=2**22
                ) as ws:
                    log.info("moshi stt connected %s", url)

                    async def sender() -> None:
                        silence = np.zeros(_MOSHI_RATE, dtype=np.float32)
                        await ws.send(
                            msgpack.packb(
                                {"type": "Audio", "pcm": [float(x) for x in silence]},
                                use_bin_type=True,
                                use_single_float=True,
                            )
                        )
                        while True:
                            piece = await chunks.get()
                            msg = msgpack.packb(
                                {"type": "Audio", "pcm": [float(x) for x in piece]},
                                use_bin_type=True,
                                use_single_float=True,
                            )
                            await ws.send(msg)

                    async def receiver() -> None:
                        async for raw in ws:
                            data = msgpack.unpackb(raw, raw=False)
                            if isinstance(data, dict):
                                captioner.on_message(data)

                    send_task = asyncio.create_task(sender())
                    recv_task = asyncio.create_task(receiver())
                    done, pending_tasks = await asyncio.wait(
                        {send_task, recv_task}, return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in pending_tasks:
                        task.cancel()
                    for task in done:
                        if not task.cancelled() and task.exception():
                            raise task.exception()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("moshi stt reconnecting (%s)", exc)
                await asyncio.sleep(1.0)

    ingest_task = asyncio.create_task(ingest())
    pump_task = asyncio.create_task(pump())
    try:
        await asyncio.wait({ingest_task, pump_task}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        ingest_task.cancel()
        pump_task.cancel()
