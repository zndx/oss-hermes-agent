"""Engine-local WebRTC: loop a forward-sim clip as the outbound media.

Not zndx.engine.v1. Signaling is HermesEngine.WebRtcOffer (SDP). Media is
UDP from this process (host net; bwrap shares net). Inbound tracks (laptop
mic) are accepted so the PC is duplex-ready; this slice does not STT them.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from hsengine.config import get_str

log = logging.getLogger("hsengine.engine.webrtc")

ICE_SERVERS = ["stun:stun.l.google.com:19302"]
ICE_TIMEOUT_S = 5.0

_FIXTURE = Path(__file__).resolve().parents[1] / "media" / "fixtures" / "demo.mp4"


class WebRtcUnavailable(RuntimeError):
    """aiortc extra is not installed."""


def video_path() -> Path | None:
    try:
        configured = get_str("hermes.engine.webrtc.video")
    except Exception:
        configured = ""
    for raw in (configured, str(_FIXTURE)):
        if not raw:
            continue
        path = Path(raw)
        if path.is_file():
            return path
    return None


class WebRtcHub:
    def __init__(self) -> None:
        self._pcs: dict[str, object] = {}
        self._players: dict[str, object] = {}

    async def offer(self, sdp: str, typ: str = "offer") -> dict[str, str]:
        try:
            from aiortc import (
                RTCConfiguration,
                RTCIceServer,
                RTCPeerConnection,
                RTCSessionDescription,
            )
            from aiortc.contrib.media import MediaPlayer
        except ImportError as e:
            raise WebRtcUnavailable("aiortc is not installed (hermes-agent[engine])") from e

        src = video_path()
        if src is None:
            raise FileNotFoundError(
                "no WebRTC source clip; set HERMES_WEBRTC_VIDEO or place demo.mp4"
            )

        config = RTCConfiguration(
            iceServers=[RTCIceServer(urls=list(ICE_SERVERS))] if ICE_SERVERS else []
        )
        pc = RTCPeerConnection(configuration=config)
        session_id = uuid.uuid4().hex[:12]
        self._pcs[session_id] = pc

        player = MediaPlayer(str(src), loop=True)
        self._players[session_id] = player
        if player.video:
            pc.addTrack(player.video)
        if player.audio:
            pc.addTrack(player.audio)
        if player.video is None and player.audio is None:
            await self._drop(session_id)
            raise FileNotFoundError(f"no audio/video tracks in {src}")

        @pc.on("connectionstatechange")
        async def _on_state() -> None:
            log.info("webrtc %s state=%s", session_id, pc.connectionState)
            if pc.connectionState in ("failed", "closed", "disconnected"):
                await self._drop(session_id)

        @pc.on("track")
        def _on_track(track) -> None:
            log.info("webrtc %s inbound %s", session_id, track.kind)

        await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type=typ or "offer"))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        await _ice_complete(pc)
        return {
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type,
            "session_id": session_id,
            "source": str(src),
        }

    async def _drop(self, session_id: str) -> None:
        player = self._players.pop(session_id, None)
        if player is not None:
            for media in (getattr(player, "video", None), getattr(player, "audio", None)):
                if media is None:
                    continue
                try:
                    media.stop()
                except Exception:
                    log.debug("webrtc stop track %s", session_id, exc_info=True)
        pc = self._pcs.pop(session_id, None)
        if pc is None:
            return
        try:
            await pc.close()  # type: ignore[union-attr]
        except Exception:
            log.debug("webrtc close %s", session_id, exc_info=True)


async def _ice_complete(pc: object, timeout: float | None = None) -> None:
    limit = ICE_TIMEOUT_S if timeout is None else timeout
    if getattr(pc, "iceGatheringState", "") == "complete":
        return
    done = asyncio.Event()

    @pc.on("icegatheringstatechange")  # type: ignore[attr-defined]
    def _() -> None:
        if getattr(pc, "iceGatheringState", "") == "complete":
            done.set()

    try:
        await asyncio.wait_for(done.wait(), timeout=limit)
    except asyncio.TimeoutError:
        log.warning("webrtc ICE gathering timed out; sending partial SDP")


HUB = WebRtcHub()
