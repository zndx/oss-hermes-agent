"""Session-scoped provider/model overlay.

A long-lived session (voice call, desktop pane, lattice Activity) may need a
different endpoint than the process default. Plugins and extras register
callables; the first that returns a dict wins. Not an env var.

Entry points: group ``hermes_agent.session_runtime`` (callables returning
``dict | None``).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

ENTRY_POINTS_GROUP = "hermes_agent.session_runtime"

OverlayFn = Callable[[], dict[str, Any] | None]

_overlays: list[OverlayFn] = []
_entry_points_loaded = False


def register_overlay(fn: OverlayFn) -> OverlayFn:
    """Register a session overlay. First non-None dict wins. Returns *fn* for decorator use."""
    if fn not in _overlays:
        _overlays.append(fn)
    return fn


def clear_overlays() -> None:
    """Tests only: drop registered overlays and the entry-point cache."""
    global _entry_points_loaded
    _overlays.clear()
    _entry_points_loaded = False


def _load_entry_points() -> None:
    global _entry_points_loaded
    if _entry_points_loaded:
        return
    _entry_points_loaded = True
    try:
        from importlib.metadata import entry_points
    except ImportError:
        return
    try:
        eps = entry_points()
        group = eps.select(group=ENTRY_POINTS_GROUP) if hasattr(eps, "select") else eps.get(ENTRY_POINTS_GROUP, [])
        for ep in group:
            try:
                fn = ep.load()
            except Exception:
                log.debug("session runtime entry point %s failed to load", ep.name, exc_info=True)
                continue
            if callable(fn):
                register_overlay(fn)
    except Exception:
        log.debug("session runtime entry points unavailable", exc_info=True)


def overlay_runtime() -> dict[str, Any] | None:
    """First overlay that returns a dict, or None (use the process default)."""
    _load_entry_points()
    for fn in list(_overlays):
        try:
            ov = fn()
        except Exception:
            log.debug("session runtime overlay %r failed", fn, exc_info=True)
            continue
        if isinstance(ov, dict) and ov:
            return ov
    return None
