"""WebRTC interactive posture: agent-rtc + Cerebras thinking.

Enter on the first RTC session, leave on the last hangup. No silent
fallback to local Qwen thinking or tiny.en.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import httpx

from hsengine.engine.federation import CompleteResult
from hsengine.engine.generated.zndx.engine.v1 import engine_pb2 as zpb
from hsengine.engine.generated.zndx.engine.v1 import engine_pb2_grpc as zpb_grpc
from hsengine.engine.yk_sentinel import (
    CEREBRAS_WORKLOAD_ID,
    apply_cerebras_thinking,
    delete_sentinel,
    moshi_serving,
    wait_admitted,
)

log = logging.getLogger("hsengine.engine.interactive")

_mu = threading.Lock()
_refcount = 0
_active = False


def is_active() -> bool:
    with _mu:
        return _active


def _cfg(path: str, default: str) -> str:
    try:
        from hsengine.config import get_str

        value = get_str(path)
        return value if value else default
    except Exception:
        return default


def _cerebras_key() -> str:
    key = (os.environ.get("CEREBRAS_API_KEY") or "").strip()
    if not key:
        raise RuntimeError(
            "DENY: CEREBRAS_API_KEY required to enter agent-rtc interactive posture"
        )
    return key


def _control_url() -> str:
    return _cfg("hermes.engine.webrtc.interactive.control", "http://127.0.0.1:5081")


def _gaius_target() -> str:
    from hsengine.engine import federation

    peers = federation.federation_peers()
    return peers[0] if peers else "127.0.0.1:50051"


def complete_cerebras(
    *,
    prompt: str,
    system_prompt: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> CompleteResult:
    key = _cerebras_key()
    model = _cfg("hermes.engine.webrtc.interactive.cerebras_model", "qwen-3.8-27b")
    base = _cfg("hermes.engine.webrtc.interactive.cerebras_url", "https://api.cerebras.ai/v1").rstrip("/")
    effort = _cfg("hermes.engine.webrtc.interactive.reasoning_effort", "low")
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "reasoning_effort": effort,
    }
    with httpx.Client(timeout=120.0) as client:
        r = client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
        )
        r.raise_for_status()
        data = r.json()
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    usage = data.get("usage") or {}
    return CompleteResult(
        text=(msg.get("content") or "").strip(),
        model=data.get("model") or model,
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        latency_ms=0.0,
        reasoning_content=(msg.get("reasoning") or "").strip(),
        finish_reason=choice.get("finish_reason") or "stop",
        peer="cerebras",
        capability="thinking",
    )


def _yield_gaius_thinking() -> None:
    import grpc

    target = _gaius_target()
    # First configured peer is gaius thinking in base.conf.
    if "50151" in target:
        target = "127.0.0.1:50051"
    wid = _cfg("hermes.engine.webrtc.interactive.thinking_workload", "gaius-thinking")
    with grpc.insecure_channel(target) as ch:
        stub = zpb_grpc.EngineStub(ch)
        reply = stub.Yield(
            zpb.YieldRequest(workload_id=wid, reason=zpb.YIELD_REASON_PREEMPTED),
            timeout=15,
        )
    log.info("yielded %s ended=%s msg=%s", wid, reply.process_ended, reply.message)


def _moshi_on() -> None:
    url = _control_url().rstrip("/")
    with httpx.Client(timeout=180.0) as client:
        r = client.post(f"{url}/interactive/on")
        r.raise_for_status()
        body = r.json()
    if not body.get("ok"):
        raise RuntimeError(body.get("error") or "moshi supervisor refused activate")
    if not moshi_serving():
        raise RuntimeError("moshi-server not listening after activate")


def _moshi_off() -> None:
    url = _control_url().rstrip("/")
    try:
        with httpx.Client(timeout=30.0) as client:
            client.post(f"{url}/interactive/off")
    except Exception:
        log.warning("moshi supervisor deactivate failed", exc_info=True)


def enter() -> None:
    global _refcount, _active
    with _mu:
        _refcount += 1
        if _refcount > 1 and _active:
            return
    _cerebras_key()
    try:
        _yield_gaius_thinking()
        apply_cerebras_thinking()
        wait_admitted(CEREBRAS_WORKLOAD_ID, timeout_s=60)
        _moshi_on()
    except Exception:
        with _mu:
            _refcount = max(0, _refcount - 1)
            _active = False
        _moshi_off()
        delete_sentinel(CEREBRAS_WORKLOAD_ID)
        raise
    with _mu:
        _active = True
    log.info("agent-rtc interactive posture on")


def leave() -> None:
    global _refcount, _active
    with _mu:
        _refcount = max(0, _refcount - 1)
        if _refcount > 0:
            return
        _active = False
    _moshi_off()
    delete_sentinel(CEREBRAS_WORKLOAD_ID)
    log.info("agent-rtc interactive posture off; Gaius thinking-ready may restore local Qwen")


async def enter_async() -> None:
    await asyncio.to_thread(enter)


async def leave_async() -> None:
    await asyncio.to_thread(leave)
