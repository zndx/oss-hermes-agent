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


def test_opening_without_material_stays_a_short_greeting():
    prompt, system, max_tokens = opening_prompt({})
    assert "Greet the listener" in prompt
    assert max_tokens == 48
