"""WebRTC interactive posture: agent-rtc + Cerebras thinking.

Enter on the first RTC session, leave on the last hangup. No silent
fallback to local Qwen thinking or tiny.en.

The posture is DECLARED to the federation as a coordination Activity
(kind ``interactive_session``) through this engine → Signals → Airflow.
Claims on that Activity ARE the YuniKorn configuration; Signals applies
them. This process never talks to Kubernetes. Postures are what peers
honour (gaius cedes its thinking uptime while the activity runs). A
session that cannot be declared is denied. Leaving releases the activity;
peers restore their own desired sets from the release (or from the
horizon if Signals is unreachable).
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import httpx

from hsengine.engine import coordination
from hsengine.engine.federation import CompleteResult
from hsengine.engine.yk_sentinel import QUEUE as AGENT_RTC_QUEUE, moshi_serving

log = logging.getLogger("hsengine.engine.interactive")

_mu = threading.Lock()
_refcount = 0
_active = False
_lease: coordination.ActivityLease | None = None


def is_active() -> bool:
    with _mu:
        return _active


def current_activity() -> dict | None:
    with _mu:
        return dict(_lease.activity) if _lease is not None else None


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
        try:
            from hermes_constants import get_hermes_home

            env_path = get_hermes_home() / ".env"
            for line in env_path.read_text().splitlines():
                if line.startswith("CEREBRAS_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip("'").strip('"')
                    break
        except OSError:
            key = ""
    if not key:
        raise RuntimeError(
            "DENY: CEREBRAS_API_KEY required to enter agent-rtc interactive posture"
        )
    return key


def _control_url() -> str:
    return _cfg("hermes.engine.webrtc.interactive.control", "http://127.0.0.1:5081")


def complete_cerebras(
    *,
    prompt: str,
    system_prompt: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.7,
    reasoning_effort: str | None = None,
) -> CompleteResult:
    key = _cerebras_key()
    model = _cfg("hermes.engine.webrtc.interactive.cerebras_model", "qwen-3.8-27b")
    base = _cfg("hermes.engine.webrtc.interactive.cerebras_url", "https://api.cerebras.ai/v1").rstrip("/")
    effort = reasoning_effort or _cfg("hermes.engine.webrtc.interactive.reasoning_effort", "low")
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
    text = (msg.get("content") or "").strip()
    result = CompleteResult(
        text=text,
        model=data.get("model") or model,
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        latency_ms=0.0,
        reasoning_content=(msg.get("reasoning") or "").strip(),
        finish_reason=choice.get("finish_reason") or "stop",
        peer="cerebras",
        capability="thinking",
    )
    spoken = spoken_text(text)
    if spoken:
        threading.Thread(
            target=_speak_cerebras,
            args=(spoken,),
            daemon=True,
            name="cerebras-tts",
        ).start()
    return result


def spoken_text(text: str) -> str:
    """Plain words for Kyutai TTS — no markdown or URLs."""
    import re

    t = " ".join((text or "").split())
    t = re.sub(r"```[\s\S]*?```", " ", t)
    t = re.sub(r"`+", "", t)
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"[#*_\[\]]+", " ", t)
    return " ".join(t.split())


def _speak_cerebras(text: str) -> None:
    try:
        from hsengine.engine.webrtc_tts import speak_on_session_boards

        log.info("speaking %r", text[:200])
        speak_on_session_boards(text, source="cerebras")
    except Exception:
        log.exception("Kyutai TTS failed for Cerebras text")


def _moshi_on() -> None:
    url = _control_url().rstrip("/")
    with httpx.Client(timeout=180.0) as client:
        r = client.post(f"{url}/interactive/on")
        if r.status_code >= 400:
            detail = r.text
            raise RuntimeError(f"moshi supervisor {r.status_code}: {detail}")
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


def _require_declared_workload(activity: dict) -> None:
    """Signals must echo the agent-rtc GPU claim and leave the Activity in force.

    Those claims are the local YuniKorn configuration; Signals applies them.
    Cerebras thinking is remote token-metered and must not appear as a GPU
    floor. Missing claims or a non-in-force state means Connect is denied.
    """
    claims = {
        (str(c.get("leaf") or ""), int(c.get("gpu") or 0))
        for c in (activity.get("claims") or [])
        if isinstance(c, dict)
    }
    needed = {(AGENT_RTC_QUEUE, 1)}
    if not needed <= claims:
        raise RuntimeError(
            "DENY: Signals did not echo the agent-rtc workload claims on the "
            f"declared activity (got {sorted(claims)!r})"
        )
    for leaf, gpu in claims:
        if str(leaf).startswith("root.external.") and gpu:
            raise RuntimeError(
                f"DENY: {leaf} is external (Cerebras/token-metered) and must not "
                f"claim local GPUs (gpu={gpu})"
            )
    state = str(activity.get("state") or "")
    if state not in coordination.IN_FORCE:
        raise RuntimeError(
            f"DENY: declared activity is not in force (state={state!r})"
        )


def enter(owner: str = "webrtc") -> None:
    """Enter the interactive posture. Order: declare the Activity to the
    federation (via this engine → Signals; Signals applies the YK claims),
    then start moshi. Any failure releases what was declared and re-raises."""
    global _refcount, _active, _lease
    with _mu:
        _refcount += 1
        if _refcount > 1 and _active:
            return
    _cerebras_key()
    lease: coordination.ActivityLease | None = None
    try:
        lease = coordination.declare_interactive(owner)
        _require_declared_workload(lease.activity)
        _moshi_on()
    except Exception as e:
        with _mu:
            _refcount = max(0, _refcount - 1)
            _active = False
            _lease = None
        _moshi_off()
        if lease is not None:
            lease.release(f"aborted: {str(e)[:120]}")
        raise
    lease.start_renewing()
    with _mu:
        _active = True
        _lease = lease
    log.info(
        "agent-rtc interactive posture on (activity %s declared to the federation; peers cede per postures)",
        lease.activity_id,
    )


def leave(outcome: str = "hangup") -> None:
    global _refcount, _active, _lease
    with _mu:
        _refcount = max(0, _refcount - 1)
        if _refcount > 0:
            return
        _active = False
        lease, _lease = _lease, None
    _moshi_off()
    if lease is not None:
        lease.release(outcome)
    log.info("agent-rtc interactive posture off; activity released — peers restore their desired sets")


async def enter_async(owner: str = "webrtc") -> None:
    await asyncio.to_thread(enter, owner)


async def leave_async(outcome: str = "hangup") -> None:
    await asyncio.to_thread(leave, outcome)
