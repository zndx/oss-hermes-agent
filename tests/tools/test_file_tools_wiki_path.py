"""``wiki/`` and ``$WIKI_PATH`` resolve to the Hermes wiki vault.

AgentRTC claimed friction-log writes that never hit the vault when a cwd
``wiki/`` skipped the rewrite. ``wiki/...`` is always the vault; a
project-local tree is ``./wiki/...``.
"""

import json
from pathlib import Path

import tools.file_tools_paths as ftp
import tools.terminal_tool as terminal_tool
from tools.file_tools import write_file_tool


def test_wiki_slash_resolves_to_vault_when_cwd_has_no_wiki(tmp_path, monkeypatch):
    vault = tmp_path / "hermes" / "wiki"
    vault.mkdir(parents=True)
    jail = tmp_path / "home-hermes"
    jail.mkdir()
    monkeypatch.chdir(jail)
    monkeypatch.setenv("WIKI_PATH", str(vault))
    monkeypatch.setattr(terminal_tool, "_session_cwd", {})

    resolved = ftp._resolve_path_for_task("wiki/concepts/alignment-structure.md", task_id="default")

    assert Path(resolved) == (vault / "concepts" / "alignment-structure.md").resolve()


def test_bare_wiki_resolves_to_vault_root(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    jail = tmp_path / "jail"
    jail.mkdir()
    monkeypatch.chdir(jail)
    monkeypatch.setenv("WIKI_PATH", str(vault))
    monkeypatch.setattr(terminal_tool, "_session_cwd", {})

    resolved = ftp._resolve_path_for_task("wiki", task_id="default")

    assert Path(resolved) == vault.resolve()


def test_dollar_wiki_path_expands_to_vault(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    jail = tmp_path / "jail"
    jail.mkdir()
    monkeypatch.chdir(jail)
    monkeypatch.setenv("WIKI_PATH", str(vault))
    monkeypatch.setattr(terminal_tool, "_session_cwd", {})

    resolved = ftp._resolve_path_for_task("$WIKI_PATH/concepts/x.md", task_id="default")
    braced = ftp._resolve_path_for_task("${WIKI_PATH}/SCHEMA.md", task_id="default")

    assert Path(resolved) == (vault / "concepts" / "x.md").resolve()
    assert Path(braced) == (vault / "SCHEMA.md").resolve()


def test_wiki_slash_is_the_vault_even_when_cwd_has_wiki(tmp_path, monkeypatch):
    vault = tmp_path / "hermes" / "wiki"
    vault.mkdir(parents=True)
    (vault / "friction.md").write_text("vault\n")
    workspace = tmp_path / "project"
    local = workspace / "wiki"
    local.mkdir(parents=True)
    (local / "README.md").write_text("project wiki\n")
    monkeypatch.chdir(workspace)
    monkeypatch.setenv("WIKI_PATH", str(vault))
    monkeypatch.setattr(terminal_tool, "_session_cwd", {})
    terminal_tool.record_session_cwd("default", str(workspace))

    resolved = ftp._resolve_path_for_task("wiki/friction.md", task_id="default")
    local_dot = ftp._resolve_path_for_task("./wiki/README.md", task_id="default")

    assert Path(resolved) == (vault / "friction.md").resolve()
    assert Path(local_dot) == (local / "README.md").resolve()


def test_wiki_slash_uses_hermes_home_when_wiki_path_unset(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    (home / "wiki").mkdir(parents=True)
    jail = tmp_path / "jail"
    jail.mkdir()
    monkeypatch.chdir(jail)
    monkeypatch.delenv("WIKI_PATH", raising=False)
    monkeypatch.setattr(terminal_tool, "_session_cwd", {})
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: home)

    resolved = ftp._resolve_path_for_task("wiki/SCHEMA.md", task_id="default")

    assert Path(resolved) == (home / "wiki" / "SCHEMA.md").resolve()


def test_write_file_wiki_alias_lands_and_is_verified(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    jail = tmp_path / "jail"
    jail.mkdir()
    monkeypatch.chdir(jail)
    monkeypatch.setenv("WIKI_PATH", str(vault))
    monkeypatch.setattr(terminal_tool, "_session_cwd", {})

    out = json.loads(
        write_file_tool("wiki/scratch/friction.md", "entry 5\n", task_id="default")
    )
    landed = vault / "scratch" / "friction.md"
    assert out.get("verified") is True
    assert landed.is_file()
    assert landed.read_text() == "entry 5\n"
    assert Path(out["resolved_path"]) == landed.resolve()
