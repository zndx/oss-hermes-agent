"""Load the project's zndx.supervision.v1 instance (follow Gaius).

Nautilus (external, agent-free) is the supervisor. This module only locates
the instance so claim seams / docs can name it. Do not host a watcher here.
"""
from __future__ import annotations

from pathlib import Path

DEFAULT_RELATIVE = Path("config/supervision/hermes.textproto")


def instance_path(root: Path | None = None) -> Path:
    base = root or Path(__file__).resolve().parents[2]
    return base / DEFAULT_RELATIVE


def instance_exists(root: Path | None = None) -> bool:
    return instance_path(root).is_file()
