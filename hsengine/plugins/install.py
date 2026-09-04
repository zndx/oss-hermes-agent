"""Install Signals memory (and optional copies) into profile-scoped HERMES_HOME.

Memory providers must not land under repo ``plugins/memory/`` (that set is
closed). This copies the Signals memory plugin into
``get_hermes_home()/plugins/signals-memory`` so the stock loader finds it.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from hermes_constants import get_hermes_home

_SRC = Path(__file__).resolve().parent / "signals_memory"


def install(*, hermes_home: Path | None = None) -> Path:
    dest_root = Path(hermes_home or get_hermes_home()) / "plugins" / "signals-memory"
    dest_root.parent.mkdir(parents=True, exist_ok=True)
    if dest_root.exists():
        shutil.rmtree(dest_root)
    shutil.copytree(_SRC, dest_root)
    return dest_root


def main() -> None:
    path = install()
    print(f"installed Signals memory plugin → {path}")


if __name__ == "__main__":
    main()
