"""Engine-local WebRTC: loop a forward-sim clip as the outbound media.

Not zndx.engine.v1. Signaling is HermesEngine.WebRtcOffer (SDP). Media is
UDP from this process (host net; bwrap shares net). Inbound tracks (laptop
mic) are accepted so the PC is duplex-ready; this slice does not STT them.

aiortc MediaPlayer(loop=True) seeks back to PTS 0; browsers freeze after
one pass. LoopingFileTrack reopens the file and keeps PTS increasing.
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


def looping_tracks(src: Path) -> tuple[object | None, object | None]:
    """Video/audio tracks that replay *src* with monotonic PTS."""
    from aiortc import MediaStreamTrack
    from aiortc.contrib.media import MediaPlayer
    from aiortc.mediastreams import MediaStreamError

    class LoopingFileTrack(MediaStreamTrack):
        def __init__(self, path: Path, kind: str) -> None:
            super().__init__()
            self.kind = kind
            self._path = path
            self._player: object | None = None
            self._inner: object | None = None
            self._offset = 0
            self._last_pts: int | None = None

        def _ensure(self) -> None:
            if self._inner is not None:
                return
            player = MediaPlayer(str(self._path))
            inner = player.video if self.kind == "video" else player.audio
            if inner is None:
                raise FileNotFoundError(f"no {self.kind} track in {self._path}")
            self._player = player
            self._inner = inner

        def _close_inner(self) -> None:
            inner, self._inner = self._inner, None
            self._player = None
            if inner is None:
                return
            try:
                inner.stop()
            except Exception:
                log.debug("webrtc stop inner %s", self.kind, exc_info=True)

        async def recv(self):
            if self.readyState != "live":
                raise MediaStreamError
            while True:
                self._ensure()
                try:
                    frame = await self._inner.recv()  # type: ignore[union-attr]
                except MediaStreamError:
                    self._close_inner()
                    if self._last_pts is not None:
                        self._offset = self._last_pts + 1
                    continue
                pts = getattr(frame, "pts", None)
                if pts is not None:
                    frame.pts = int(pts) + self._offset
                    self._last_pts = frame.pts
                return frame

        def stop(self) -> None:
            self._close_inner()
            super().stop()

    probe = MediaPlayer(str(src))
    has_video = probe.video is not None
    has_audio = probe.audio is not None
    for media in (probe.video, probe.audio):
        if media is None:
            continue
        try:
            media.stop()
        except Exception:
            log.debug("webrtc stop probe", exc_info=True)
    video = LoopingFileTrack(src, "video") if has_video else None
    audio = LoopingFileTrack(src, "audio") if has_audio else None
    return video, audio


class WebRtcHub:
    def __init__(self) -> None:
        self._pcs: dict[str, object] = {}
        self._tracks: dict[str, list[object]] = {}
        self._tasks: dict[str, list[asyncio.Task]] = {}

    async def offer(self, sdp: str, typ: str = "offer") -> dict[str, str]:
        try:
            from aiortc import (
                RTCConfiguration,
                RTCIceServer,
                RTCPeerConnection,
                RTCSessionDescription,
            )
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

        from hsengine.engine.webrtc_captions import CaptionBoard, caption_track
        from hsengine.engine.webrtc_stt import follow_audio, load_model, stt_available

        board = CaptionBoard()
        loop = asyncio.get_running_loop()
        if stt_available():
            loop.run_in_executor(None, load_model)
        video, audio = looping_tracks(src)
        tracks: list[object] = []
        if video is not None:
            painted = caption_track(video, board) if stt_available() else video
            pc.addTrack(painted)  # type: ignore[arg-type]
            tracks.append(painted)
        if audio is not None:
            pc.addTrack(audio)  # type: ignore[arg-type]
            tracks.append(audio)
        if not tracks:
            await self._drop(session_id)
            raise FileNotFoundError(f"no audio/video tracks in {src}")
        self._tracks[session_id] = tracks

        @pc.on("connectionstatechange")
        async def _on_state() -> None:
            log.info("webrtc %s state=%s", session_id, pc.connectionState)
            if pc.connectionState in ("failed", "closed"):
                await self._drop(session_id)

        @pc.on("track")
        def _on_track(track) -> None:
            log.info("webrtc %s inbound %s", session_id, track.kind)
            if track.kind != "audio" or not stt_available():
                return
            task = loop.create_task(follow_audio(track, board))
            self._tasks.setdefault(session_id, []).append(task)

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

    async def hangup(self, session_id: str) -> bool:
        if session_id not in self._pcs and session_id not in self._tracks:
            return False
        await self._drop(session_id)
        return True

    async def _drop(self, session_id: str) -> None:
        for task in self._tasks.pop(session_id, []):
            task.cancel()
        for track in self._tracks.pop(session_id, []):
            try:
                track.stop()  # type: ignore[union-attr]
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
