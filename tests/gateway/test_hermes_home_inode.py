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


def test_setproctitle_hermes_still_matches_gateway_record(monkeypatch, tmp_path: Path) -> None:
    """systemd ExecStart python -m hermes_cli.main gateway run titles as 'hermes'."""
    from gateway.status import _record_matches_live_gateway_pid

    record = {
        "pid": 4242,
        "kind": "hermes-gateway",
        "argv": ["/opt/venv/bin/python", "-m", "hermes_cli.main", "gateway", "run"],
        "hermes_home": str(tmp_path),
        "gateway_state": "running",
    }
    monkeypatch.setattr("gateway.status._read_process_cmdline", lambda pid: "hermes")
    monkeypatch.setattr("gateway.status._pid_exists", lambda pid: True)
    assert _record_matches_live_gateway_pid(record, 4242, expected_home=tmp_path)
    assert not _record_matches_live_gateway_pid(record, 4242, expected_home=tmp_path / "other")


def test_same_hermes_home_distinct_dirs(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert not _same_hermes_home(a, b)
