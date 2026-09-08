"""Silence hazard: first poke ~60–90s, by 3 min actively exploring."""
from __future__ import annotations

from hsengine.engine.webrtc_silence import (
    IDLE_ARM_S,
    cue_gap_s,
    director_prompts,
    exploration_phase,
    fire_probability,
    hazard_lambda,
    idle_frac,
)


def test_no_hazard_before_one_minute():
    assert idle_frac(59.9) == 0.0
    assert hazard_lambda(59.9) == 0.0
    assert fire_probability(59.9) == 0.0


def test_first_window_is_mostly_sixty_to_ninety():
    # P(wait < 30s | armed) = 1 - exp(-30/22) ≈ 0.74
    lam = hazard_lambda(IDLE_ARM_S + 0.01)
    p30 = 1.0 - __import__("math").exp(-lam * 30.0)
    assert 0.65 < p30 < 0.85
    assert exploration_phase(75.0) == "nudge"
    system, prompt, max_tokens, tools = director_prompts(75.0)
    assert tools is True
    assert "conversation" in system.lower()
    assert max_tokens <= 90


def test_three_minutes_is_novel_and_hotter():
    assert exploration_phase(180.0) == "novel"
    assert hazard_lambda(180.0) > 3 * hazard_lambda(61.0)
    assert cue_gap_s(180.0) < cue_gap_s(61.0)
    system, prompt, max_tokens, tools = director_prompts(180.0)
    assert tools is True
    assert "HN" in system or "Hacker" in system
    assert "FMP" in system or "market" in system.lower()
    assert max_tokens >= 200


def test_novel_silence_speaks_from_cognition_glance():
    glance = "Attending ADMIT prospects fmp: SLB 10-K. HN: Show HN: aperture. FMP: SLB"
    system, prompt, max_tokens, tools = director_prompts(180.0, glance=glance)
    assert tools is True
    assert "attention-schema" in system.lower() or "upper buffer" in system.lower()
    assert "Cognition glance" in prompt
    assert "Show HN: aperture" in prompt
    assert "web-search unless" in system.lower() or "Do not web-search" in system


def test_should_fire_respects_busy_and_speaking():
    from hsengine.engine.webrtc_silence import SilenceDirector

    class Turns:
        busy = True
        last_user_at = 0.0

        def try_claim(self):
            return False

    class Speech:
        def speaking(self):
            return False

    now = [200.0]
    d = SilenceDirector(
        loop=None,  # type: ignore[arg-type]
        session_id="x",
        turns=Turns(),
        speech=Speech(),
        rng=lambda: 0.0,
        now=lambda: now[0],
    )
    d._quiet_since = 0.0
    assert d.should_fire() is False
    d._turns.busy = False

    class QuietTurns:
        busy = False
        last_user_at = 0.0

        def try_claim(self):
            return True

    d._turns = QuietTurns()
    assert d.should_fire() is True


def test_novel_cue_fetches_cognition_glance(monkeypatch):
    import asyncio

    from hsengine.engine import ops
    from hsengine.engine.webrtc_silence import SilenceDirector

    seen = {"glance": 0}

    def _glance(**_k):
        seen["glance"] += 1
        return {
            "ok": True,
            "note": "gaius: HN: Show HN: aperture. FMP: SLB",
            "hits": [{"source": "hn", "title": "Show HN: aperture", "snippet": "membrane"}],
        }

    class Turns:
        busy = False
        last_user_at = 0.0
        claimed = False

        def try_claim(self):
            self.claimed = True
            return True

        def release(self):
            self.claimed = False

    class Speech:
        def speaking(self):
            return False

    monkeypatch.setattr(ops, "cognition_glance", _glance)
    monkeypatch.setattr(
        "hsengine.engine.interactive.complete_cerebras",
        lambda **k: type("R", (), {"text": "ok", "model": "x"})(),
    )
    monkeypatch.setattr("hsengine.engine.session_history.record_turn", lambda *a, **k: None)

    d = SilenceDirector(
        loop=None,  # type: ignore[arg-type]
        session_id="x",
        turns=Turns(),
        speech=Speech(),
        rng=lambda: 0.0,
        now=lambda: 200.0,
    )
    d._quiet_since = 0.0
    asyncio.run(d._cue())
    assert seen["glance"] == 1
