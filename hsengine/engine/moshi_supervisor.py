"""Resident moshi-server supervisor for devenv.

Always listens on the control port. CUDA moshi-server starts only on
POST /interactive/on (WebRTC session) and stops on POST /interactive/off.
YuniKorn claims are Signals' job (the engine declares the Activity first).
This process never talks to Kubernetes. No whisper/CPU path.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from hsengine.engine.yk_sentinel import (
    WORKLOAD_ID,
    lease_one_gpu,
    moshi_serving,
    release_gpu_lease,
)

log = logging.getLogger("hsengine.engine.moshi_supervisor")

CONTROL_PORT = int(os.environ.get("MOSHI_CONTROL_PORT", "5081"))
MOSHI_PORT = int(os.environ.get("MOSHI_STT_PORT", "5080"))
ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".devenv" / "state" / "moshi"
PID_FILE = STATE / "moshi-stt.pid"

_mu = threading.Lock()
_worker: subprocess.Popen | None = None


def _moshi_env(gpu: int) -> dict[str, str]:
    """CUDA_VISIBLE_DEVICES only. Library path is the devenv moshi-server wrap."""
    env = os.environ.copy()
    profile_bin = ROOT / ".devenv" / "profile" / "bin"
    cargo_bin = Path.home() / ".cargo" / "bin"
    env["PATH"] = f"{profile_bin}:{env.get('PATH', '')}:{cargo_bin}"
    env["CUDA_HOME"] = env.get("CUDA_HOME", "/usr/local/cuda")
    env["CUDA_VISIBLE_DEVICES"] = str(gpu)
    env["HF_HOME"] = env.get("HF_HOME", "/raid/cache/huggingface")
    return env


def activate() -> dict:
    global _worker
    with _mu:
        if _worker is not None and _worker.poll() is None and moshi_serving(port=MOSHI_PORT):
            return {"ok": True, "moshi": True, "already": True}
        binary = shutil_which("moshi-server")
        if not binary:
            raise RuntimeError("moshi-server not on PATH")
        gpu = lease_one_gpu(os.getpid())
        STATE.mkdir(parents=True, exist_ok=True)
        (STATE / "static").mkdir(exist_ok=True)
        (STATE / "logs").mkdir(exist_ok=True)
        config = os.environ.get("MOSHI_STT_CONFIG", str(ROOT / "hsengine/moshi/stt-1b.toml"))
        _worker = subprocess.Popen(
            [binary, "worker", "--config", config, "--port", str(MOSHI_PORT)],
            cwd=str(STATE),
            env=_moshi_env(gpu),
            stdout=subprocess.DEVNULL,
            stderr=None,
        )
        PID_FILE.write_text(str(_worker.pid))
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if _worker.poll() is not None:
                raise RuntimeError(f"moshi-server exited {_worker.returncode}")
            if moshi_serving(port=MOSHI_PORT):
                log.info("moshi-server listening on :%s gpu=%s", MOSHI_PORT, gpu)
                return {"ok": True, "moshi": True, "gpu": gpu}
            time.sleep(0.4)
        raise RuntimeError("moshi-server did not listen on :5080")


def shutil_which(name: str) -> str | None:
    import shutil

    return shutil.which(name)


def deactivate() -> dict:
    global _worker
    with _mu:
        proc, _worker = _worker, None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        PID_FILE.unlink(missing_ok=True)
        release_gpu_lease()
        return {"ok": True, "moshi": False}


def status() -> dict:
    alive = _worker is not None and _worker.poll() is None
    return {
        "ok": True,
        "supervisor": True,
        "moshi": moshi_serving(port=MOSHI_PORT),
        "worker": alive,
        "workload_id": WORKLOAD_ID,
    }


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        log.info("%s " + fmt, self.address_string(), *args)

    def _json(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/health":
            self._json(200, status())
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.rstrip("/")
        try:
            if path == "/interactive/on":
                self._json(200, activate())
                return
            if path == "/interactive/off":
                self._json(200, deactivate())
                return
        except Exception as e:
            log.exception("supervisor %s failed", path)
            self._json(503, {"ok": False, "error": str(e)})
            return
        self._json(404, {"ok": False, "error": "not found"})


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cargo_bin = Path.home() / ".cargo" / "bin"
    os.environ["PATH"] = f"{cargo_bin}:{os.environ.get('PATH', '')}"
    server = ThreadingHTTPServer(("127.0.0.1", CONTROL_PORT), _Handler)

    def _stop(*_args) -> None:
        try:
            deactivate()
        finally:
            threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("moshi supervisor control :%s (moshi-server on :%s when interactive)", CONTROL_PORT, MOSHI_PORT)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
