"""HERMES_HOME identity across bind-mount aliases (dashboard bwrap)."""

from __future__ import annotations

from pathlib import Path

from gateway.status import _same_hermes_home


def test_same_hermes_home_symlink_is_same(tmp_path: Path) -> None:
    real = tmp_path / "host"
    real.mkdir()
    alias = tmp_path / "jail"
    alias.symlink_to(real)
    assert _same_hermes_home(real, alias)
    assert _same_hermes_home(str(real), str(alias))


def test_same_hermes_home_distinct_dirs(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert not _same_hermes_home(a, b)
