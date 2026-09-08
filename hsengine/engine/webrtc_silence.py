"""Stochastic silence clock for AgentRTC self-initiated exploration.

User-idle under 60s is dead air. From 60s the hazard ramps so the first
poke typically lands in the 60–90s window; by 180s the rate is high and
the prompt tells the model to search novel domains (HN, markets, KB).
Director cues never barge TTS or a user turn.
"""
from __future__ import annotations

import asyncio
import logging
import math
import random
import time
from typing import Any, Callable

log = logging.getLogger("hsengine.engine.webrtc.silence")

IDLE_ARM_S = 60.0
IDLE_FULL_S = 180.0
TICK_S = 2.0
LAMBDA_ARM = 1.0 / 22.0  # ~74% of first fires by 90s
LAMBDA_FULL = 1.0 / 7.0
GAP_ARM_S = 14.0
GAP_FULL_S = 5.0


def idle_frac(user_idle_s: float) -> float:
    if user_idle_s < IDLE_ARM_S:
        return 0.0
    return min(1.0, (user_idle_s - IDLE_ARM_S) / (IDLE_FULL_S - IDLE_ARM_S))


def hazard_lambda(user_idle_s: float) -> float:
    x = idle_frac(user_idle_s)
    if x <= 0.0:
        return 0.0
    return LAMBDA_ARM + (LAMBDA_FULL - LAMBDA_ARM) * (x * x)


def cue_gap_s(user_idle_s: float) -> float:
    x = idle_frac(user_idle_s)
    return GAP_ARM_S + (GAP_FULL_S - GAP_ARM_S) * x


def fire_probability(user_idle_s: float, dt: float = TICK_S) -> float:
    lam = hazard_lambda(user_idle_s)
    if lam <= 0.0 or dt <= 0.0:
        return 0.0
    return 1.0 - math.exp(-lam * dt)


def exploration_phase(user_idle_s: float) -> str:
    if user_idle_s < 90.0:
        return "nudge"
    if user_idle_s < 150.0:
        return "adjacent"
    return "novel"


def director_prompts(user_idle_s: float) -> tuple[str, str, int, bool]:
    """system, user prompt, max_tokens, tools."""
    phase = exploration_phase(user_idle_s)
    idle = int(user_idle_s)
    if phase == "nudge":
        system = (
            "You are Hermes in an AgentRTC pause. Plain spoken words only. "
            "Call narrative to see which slide this minute belongs to, then "
            "offer one small thread from that place. Two sentences, then stop. "
            "Do not web-search. Do not greet. Do not mention the silence."
        )
        prompt = f"A {idle}s pause. Check narrative, one small thread. Stop."
        return system, prompt, 90, True
    if phase == "adjacent":
        system = (
            "You are Hermes in a lengthening AgentRTC pause. Plain spoken "
            "words only. Call narrative first. You may kb_search or web_search "
            "once for something adjacent. Then 2–4 sentences from that place. "
            "Stop. Do not greet. Do not mention the silence."
        )
        prompt = f"A {idle}s pause. Narrative, then adjacent if useful. Stop."
        return system, prompt, 160, True
    system = (
        "You are Hermes in a long AgentRTC silence. Plain spoken words only. "
        "Call narrative first so you know where the running story is. "
        "Then actively explore a novel domain in the parlance of our time: "
        "Hacker News front page, markets/FMP watchlist, or a surprising "
        "adjacent idea. Call web_search and/or kb_search. Then speak a few sentences "
        "that could reinvigorate the conversation. Stop. Do not greet. Do not "
        "apologize for the pause."
    )
    prompt = (
        f"A {idle}s silence. Search HN or FMP or the KB for something new. "
        "Then speak. Stop."
    )
    return system, prompt, 220, True


class SilenceDirector:
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        *,
        session_id: str,
        turns: Any,
        speech: Any | None,
        rng: Callable[[], float] | None = None,
        now: Callable[[], float] | None = None,
    ) -> None:
        self._loop = loop
        self._session_id = session_id
        self._turns = turns
        self._speech = speech
        self._rng = rng or random.random
        self._now = now or time.monotonic
        self._last_cue = 0.0
        self._quiet_since = self._now()

    def note_speech_playing(self, playing: bool) -> None:
        if not playing:
            self._quiet_since = self._now()

    def _user_idle(self) -> float:
        last = float(getattr(self._turns, "last_user_at", 0.0) or 0.0)
        origin = last if last > 0.0 else self._quiet_since
        return max(0.0, self._now() - origin)

    def _speaking(self) -> bool:
        sp = self._speech
        if sp is None:
            return False
        fn = getattr(sp, "speaking", None)
        if not callable(fn):
            return False
        try:
            return bool(fn())
        except Exception:
            return False

    def should_fire(self) -> bool:
        if self._speaking() or getattr(self._turns, "busy", False):
            return False
        idle = self._user_idle()
        if idle < IDLE_ARM_S:
            return False
        if self._now() - self._last_cue < cue_gap_s(idle):
            return False
        return self._rng() < fire_probability(idle, TICK_S)

    async def run(self) -> None:
        log.info("silence director on %s", self._session_id)
        was_playing = False
        try:
            while True:
                await asyncio.sleep(TICK_S)
                playing = self._speaking()
                if was_playing and not playing:
                    self._quiet_since = self._now()
                was_playing = playing
                if playing:
                    continue
                if not self.should_fire():
                    continue
                await self._cue()
        except asyncio.CancelledError:
            log.info("silence director off %s", self._session_id)
            raise

    async def _cue(self) -> None:
        claim = getattr(self._turns, "try_claim", None)
        if callable(claim):
            if not claim():
                return
        else:
            if getattr(self._turns, "busy", False):
                return
            self._turns._busy = True
        idle = self._user_idle()
        system, prompt, max_tokens, tools = director_prompts(idle)
        self._last_cue = self._now()
        log.info(
            "silence cue session=%s idle=%.0fs phase=%s tools=%s",
            self._session_id,
            idle,
            exploration_phase(idle),
            tools,
        )
        try:
            from hsengine.engine import interactive, session_history

            result = await asyncio.to_thread(
                interactive.complete_cerebras,
                prompt=prompt,
                system_prompt=system,
                max_tokens=max_tokens,
                temperature=0.6,
                reasoning_effort="none",
                tools=tools,
            )
            session_history.record_turn(
                self._session_id, assistant=result.text, model=result.model
            )
        except Exception:
            log.exception("silence cue failed")
        finally:
            rel = getattr(self._turns, "release", None)
            if callable(rel):
                rel()
            else:
                self._turns._busy = False
