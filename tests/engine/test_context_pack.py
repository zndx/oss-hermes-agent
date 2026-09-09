"""Pipeline briefs for AgentRTC openings come from agenda + thoughts tools."""
from __future__ import annotations

from hsengine.engine.context_pack import (
    conversational_context,
    pipeline_block,
    usable_spoken,
)


def test_pipeline_block_joins_spoken_briefs():
    text = pipeline_block(
        {
            "agenda_spoken": "Today is the retrospective.",
            "thoughts_spoken": "Cell state should be auditable.",
        }
    )
    assert "Today's agenda brief" in text
    assert "retrospective" in text
    assert "Latest thoughts brief" in text
    assert "auditable" in text


def test_pipeline_block_empty_when_pipelines_are_silent():
    assert pipeline_block({}) == ""
    assert pipeline_block(None) == ""
    assert pipeline_block({"agenda_spoken": "cannot reach the pipeline brief"}) == ""


def test_usable_spoken_drops_fetch_failures():
    assert usable_spoken("cannot reach the pipeline brief") == ""
    assert usable_spoken("idle") == ""
    assert usable_spoken("#CG.00000001.NOPOOL no database") == ""
    assert "retrospective" in usable_spoken(
        "Today is the AgentRTC retrospective after the voice session."
    )


def test_conversational_context_reads_spoken_briefs(monkeypatch):
    from hsengine.engine import ops

    monkeypatch.setattr(
        ops,
        "agenda",
        lambda item_id="": {
            "ok": True,
            "briefs": [{"spoken": "Today is the AgentRTC retrospective."}],
            "item": {"title": "AgentRTC retrospective", "body": "Theta after the voice."}
            if item_id
            else None,
        },
    )
    monkeypatch.setattr(
        ops,
        "recent_thoughts",
        lambda **k: {
            "ok": True,
            "briefs": [
                {
                    "spoken": "I keep thinking about verifiable cell state on the edge."
                }
            ],
        },
    )
    pack = conversational_context(agenda_id="note/today")
    assert pack["agenda_spoken"].startswith("Today is the AgentRTC")
    assert pack["thoughts_spoken"].startswith("I keep thinking")
    assert pack["agenda_title"] == "AgentRTC retrospective"
    bare = conversational_context()
    assert "agenda_title" not in bare
    assert bare["thoughts_spoken"]
