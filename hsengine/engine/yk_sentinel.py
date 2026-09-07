"""Host occupancy for the agent-rtc CUDA worker (Kyutai STT).

YuniKorn configuration is Signals' job: this engine declares the interactive
Activity (claims = queue config) over signals-protocol, and Signals applies
it. This module never talks to Kubernetes. It only:

- names the leaves (agent-rtc is the local GPU claim; token-metered is the
  remote Cerebras API and takes no local GPU)
- takes an advisory 1-GPU host lease so moshi-server does not collide with
  another local CUDA process
- knows whether moshi-server is listening
"""
from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("hsengine.engine.yk_sentinel")

WORKLOAD_ID = "hermes-agent-rtc"
QUEUE = "root.internal.inference.agent-rtc"
RESOURCE_CLASS = "internal.inference.agent-rtc"
GPU_TOKENS = 1
CEREBRAS_WORKLOAD_ID = "hermes-cerebras-thinking"
CEREBRAS_QUEUE = "root.external.token-metered"
CEREBRAS_CLASS = "external.token-metered"
LEASE_DIR = Path(os.environ.get("ZNDX_GPU_LEASE_DIR", "/tmp/zndx-gpu-leases"))


def _gpu_indices() -> list[int]:
    proc = subprocess.run(
        ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError("nvidia-smi failed — agent-rtc needs a GPU")
    return [int(line.strip()) for line in proc.stdout.splitlines() if line.strip().isdigit()]


def _live_lease_gpus() -> set[int]:
    held: set[int] = set()
    if not LEASE_DIR.is_dir():
        return held
    for path in LEASE_DIR.glob("*.owner.json"):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        pid = payload.get("pid")
        if not isinstance(pid, int) or not Path(f"/proc/{pid}").exists():
            continue
        gpus = payload.get("gpus") or payload.get("gpu") or []
        if isinstance(gpus, int):
            held.add(gpus)
        elif isinstance(gpus, list):
            for g in gpus:
                try:
                    held.add(int(g))
                except (TypeError, ValueError):
                    continue
        stem = path.stem  # gpu-5 or gpu-0-1
        if stem.startswith("gpu-"):
            for part in stem[4:].split("-"):
                if part.isdigit():
                    held.add(int(part))
    return held


def lease_one_gpu(pid: int, project: str = "hermes") -> int:
    """Take an advisory 1-GPU lease. Fail if none are free."""
    LEASE_DIR.mkdir(parents=True, exist_ok=True)
    held = _live_lease_gpus()
    for idx in _gpu_indices():
        if idx in held:
            continue
        owner = LEASE_DIR / f"gpu-{idx}.owner.json"
        if owner.exists():
            try:
                existing = json.loads(owner.read_text())
                ep = existing.get("pid")
                if isinstance(ep, int) and Path(f"/proc/{ep}").exists():
                    continue
                owner.unlink()
            except (OSError, json.JSONDecodeError, TypeError):
                continue
        payload = {
            "pid": pid,
            "project": project,
            "gpus": [idx],
            "workload_id": WORKLOAD_ID,
            "queue": QUEUE,
        }
        try:
            fd = os.open(str(owner), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            continue
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh)
        log.info("leased GPU %s for %s", idx, WORKLOAD_ID)
        return idx
    raise RuntimeError("no free GPU for agent-rtc (YK token is not a device bind)")


def release_gpu_lease() -> None:
    for path in LEASE_DIR.glob("gpu-*.owner.json"):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("workload_id") == WORKLOAD_ID:
            path.unlink(missing_ok=True)


def moshi_serving(host: str = "127.0.0.1", port: int = 5080, timeout: float = 0.4) -> bool:
    try:
        sock = socket.create_connection((host, port), timeout)
        sock.close()
        return True
    except OSError:
        return False


def pid_file() -> Path:
    return Path(
        os.environ.get("HERMES_MOSHI_PID_FILE")
        or Path(__file__).resolve().parents[2] / ".devenv/state/moshi/moshi-stt.pid"
    )


def kill_moshi() -> bool:
    path = pid_file()
    try:
        pid = int(path.read_text().strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        path.unlink(missing_ok=True)
        return False
    path.unlink(missing_ok=True)
    return True


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in {"lease", "release"}:
        print("usage: python -m hsengine.engine.yk_sentinel lease|release", file=sys.stderr)
        return 2
    if args[0] == "lease":
        print(lease_one_gpu(os.getpid()))
        return 0
    release_gpu_lease()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
