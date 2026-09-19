"""Command descriptions survive both catalog and completion transport."""

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document


def test_full_descriptions_survive_catalog_and_completion(monkeypatch):
    from agent import skill_commands
    from hermes_cli import plugins
    from hermes_cli.commands_completion import SlashCommandCompleter
    from tui_gateway import server

    description = "Read the entire description before selecting a command. " * 8
    skills = {"/proof-skill": {"name": "proof-skill", "description": description}}
    monkeypatch.setattr(skill_commands, "scan_skill_commands", lambda: skills)
    monkeypatch.setattr(plugins, "get_plugin_commands", lambda: {"proof-plugin": {"description": description}})
    monkeypatch.setattr(server, "_load_cfg", lambda: {"quick_commands": {"proof-quick": {"description": description}}})
    catalog = server._methods["commands.catalog"](1, {})["result"]
    pairs = dict(catalog["pairs"])
    for name in ("/proof-skill", "/proof-plugin", "/proof-quick"):
        assert pairs[name] == description
    completer = SlashCommandCompleter(skill_commands_provider=lambda: skills)
    completions = list(completer.get_completions(Document("/proof"), CompleteEvent()))
    assert len(completions) == 2
    assert all(description in completion.display_meta_text for completion in completions)


def test_same_named_plugin_command_hides_skill_slash(monkeypatch):
    from hermes_cli import plugins
    from hermes_cli.commands_completion import SlashCommandCompleter

    skills = {"/zettel": {"name": "zettel", "description": "Skill zettel"}}
    monkeypatch.setattr(
        plugins, "get_plugin_commands",
        lambda: {"zettel": {"description": "Plugin zettel"}},
    )
    completer = SlashCommandCompleter(skill_commands_provider=lambda: skills)
    completions = list(completer.get_completions(Document("/zettel"), CompleteEvent()))
    zettel = [c for c in completions if "zettel" in (c.text or "").replace(" ", "")]
    assert len(zettel) == 1
    meta = zettel[0].display_meta_text or ""
    assert "🔌" in meta
    assert "⚡" not in meta


def test_catalog_does_not_list_skill_when_plugin_owns_the_slash(monkeypatch):
    from agent import skill_commands
    from hermes_cli import plugins
    from tui_gateway import server

    monkeypatch.setattr(
        skill_commands, "scan_skill_commands",
        lambda: {"/zettel": {"name": "zettel", "description": "Skill zettel"}},
    )
    monkeypatch.setattr(
        plugins, "get_plugin_commands",
        lambda: {"zettel": {"description": "Plugin zettel"}},
    )
    monkeypatch.setattr(server, "_load_cfg", lambda: {})
    catalog = server._methods["commands.catalog"](1, {})["result"]
    zettel_pairs = [p for p in catalog["pairs"] if p[0] == "/zettel"]
    assert zettel_pairs == [["/zettel", "Plugin zettel"]]
    assert "/zettel" not in catalog.get("skills", {})
