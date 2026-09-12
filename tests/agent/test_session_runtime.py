"""Session runtime overlay: first non-None dict wins; not an env var."""
from __future__ import annotations

from agent import session_runtime as sr


def setup_function(_fn):
    sr.clear_overlays()


def teardown_function(_fn):
    sr.clear_overlays()


def test_overlay_none_when_nothing_registered(monkeypatch):
    monkeypatch.setattr(sr, "_load_entry_points", lambda: None)
    assert sr.overlay_runtime() is None


def test_first_non_empty_dict_wins(monkeypatch):
    monkeypatch.setattr(sr, "_load_entry_points", lambda: None)
    sr.register_overlay(lambda: None)
    sr.register_overlay(lambda: {})
    sr.register_overlay(lambda: {"provider": "fast", "model": "x"})
    sr.register_overlay(lambda: {"provider": "slow"})
    ov = sr.overlay_runtime()
    assert ov is not None
    assert ov["provider"] == "fast"
    assert ov["model"] == "x"


def test_failing_overlay_is_skipped(monkeypatch):
    monkeypatch.setattr(sr, "_load_entry_points", lambda: None)

    def _boom():
        raise RuntimeError("nope")

    sr.register_overlay(_boom)
    sr.register_overlay(lambda: {"provider": "ok"})
    assert sr.overlay_runtime()["provider"] == "ok"


def test_register_overlay_is_idempotent(monkeypatch):
    monkeypatch.setattr(sr, "_load_entry_points", lambda: None)

    def _once():
        return {"provider": "a"}

    sr.register_overlay(_once)
    sr.register_overlay(_once)
    assert sr._overlays.count(_once) == 1
