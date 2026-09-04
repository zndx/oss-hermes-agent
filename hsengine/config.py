"""HOCON config loader — the only sanctioned config entry point.

House rule: env vars enter through ``${?VAR}`` capture in config/base.conf;
application code reads ``load_config()``, never ``os.environ``.
"""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

from pyhocon import ConfigFactory, ConfigTree

_DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


@functools.lru_cache(maxsize=4)
def load_config(config_dir: Path | None = None) -> ConfigTree:
    base = (config_dir or _DEFAULT_CONFIG_DIR) / "base.conf"
    return ConfigFactory.parse_file(str(base), resolve=True)


def get_config() -> ConfigTree:
    return load_config()


def get_str(path: str) -> str:
    return str(load_config().get(path))


def get_int(path: str) -> int:
    return int(str(load_config().get(path)))


def get_list(path: str) -> list[Any]:
    value = load_config().get(path)
    if value is None:
        return []
    return list(value)


def reset_config() -> None:
    load_config.cache_clear()
