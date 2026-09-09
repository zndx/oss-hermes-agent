"""Presenterm decks stay off the calendar invite and drive the opening."""
from __future__ import annotations

from hsengine.engine.agenda_deck import opening_prompt, split_public_deck


def test_split_keeps_deck_off_the_public_lede():
    public, deck = split_public_deck(
        "A half hour to decide whether the book moves.\n\n"
        "## Deck\n\n"
        "Opening\n===\n\n"
        "Would you change the book today?\n\n"
        "<!-- speaker_note: Intel raise. -->\n"
        "<!-- end_slide -->\n"
    )
    assert "half hour" in public
    assert "speaker_note" not in public
    assert "end_slide" in deck
    assert "Would you change the book" in deck


def test_opening_uses_full_deck_when_present():
    prompt, system, max_tokens = opening_prompt(
        {
            "title": "Watchlist after the tape",
            "public": "Decide whether the book moves.",
            "deck": "Opening\n===\n\nWould you change the book today?\n",
        }
    )
    assert "Watchlist after the tape" in prompt
    assert "Would you change the book" in prompt
    assert "first slide" in system
    assert "off-script" in system
    assert "You are Hermes" not in system
    assert "casual" in system.lower() or "hello" in system.lower()
    assert max_tokens > 48


def test_opening_without_deck_uses_public_lede():
    prompt, system, max_tokens = opening_prompt(
        {
            "title": "Discover coherence check-in",
            "public": "Would you send a colleague to this screen today?",
            "deck": "",
        }
    )
    assert "Discover coherence check-in" in prompt
    assert "colleague" in prompt
    assert "Greet the listener" not in prompt
    assert max_tokens > 48


def test_narrative_at_minute_four_is_not_always_the_opening():
    deck = (
        "Opening\n===\n\nHello.\n\n<!-- end_slide -->\n\n"
        "Intel\n===\n\nTwenty-three billion.\n\n<!-- speaker_note: fumes. -->\n\n"
        "<!-- end_slide -->\n\n"
        "Lilly\n===\n\nGrowth.\n\n<!-- end_slide -->\n\n"
        "Disney\n===\n\nThe gap.\n"
    )
    material = {"title": "Watchlist", "deck": deck, "starts_ms": 0, "ends_ms": 30 * 60 * 1000}
    from hsengine.engine.agenda_deck import narrative_at, parse_slides

    assert len(parse_slides(deck)) == 4
    early = narrative_at(material, elapsed_s=4 * 60)
    late = narrative_at(material, elapsed_s=20 * 60)
    assert early["slide"] == 1
    assert early["title"] == "Opening"
    assert late["slide"] >= 3
    assert late["title"] in ("Lilly", "Disney")
    assert "fumes" in " ".join(narrative_at(material, elapsed_s=10 * 60)["notes"])


def test_opening_without_material_stays_a_short_greeting():
    prompt, system, max_tokens = opening_prompt({})
    assert "casual hello" in prompt.lower()
    assert "You are Hermes" not in system and "Hermes" not in prompt
    assert "pipeline" not in system.lower()
    assert max_tokens == 48


def test_opening_uses_pipeline_briefs_when_there_is_no_session_material():
    prompt, system, max_tokens = opening_prompt(
        {},
        pipeline={
            "agenda_spoken": "Today is the AgentRTC retrospective.",
            "thoughts_spoken": "I keep thinking about verifiable cell state.",
        },
    )
    assert "AgentRTC retrospective" in prompt
    assert "verifiable cell state" in prompt
    assert "You are Hermes" not in system
    assert "casual" in system.lower() or "hello" in system.lower()
    assert "Airflow" not in system
    assert max_tokens > 48


def test_opening_with_deck_still_carries_pipeline_briefs():
    prompt, system, _ = opening_prompt(
        {
            "title": "Watchlist after the tape",
            "public": "Decide whether the book moves.",
            "deck": "Opening\n===\n\nWould you change the book today?\n",
        },
        pipeline={"thoughts_spoken": "Contracts and molecular partner specificity."},
    )
    assert "Would you change the book" in prompt
    assert "molecular partner" in prompt
    assert "You are Hermes" not in system
    assert "do not name them" in system.lower()
