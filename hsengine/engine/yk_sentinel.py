"""YuniKorn Application claim for Hermes agent-rtc (1 GPU guaranteed).

Queue path is the resource class. Project is identity (federation.project=hermes).
Host occupancy is federation.zndx.org/gpu only — never nvidia.com/gpu on this
CPU-only pause pod (that would bind the card into an empty sentinel).

Admit (pod Running) is required before moshi-server starts CUDA. If YK does
not admit, agent-rtc is unavailable — no CPU/whisper path.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger("hsengine.engine.yk_sentinel")

WORKLOAD_ID = "hermes-agent-rtc"
QUEUE = "root.internal.inference.agent-rtc"
RESOURCE_CLASS = "internal.inference.agent-rtc"
GPU_TOKENS = 1
PRIORITY_CLASS = "zndx-gpu-high"
CEREBRAS_WORKLOAD_ID = "hermes-cerebras-thinking"
CEREBRAS_QUEUE = "root.external.token-metered"
CEREBRAS_CLASS = "external.token-metered"
NAMESPACE = os.environ.get("SIGNALS_SENTINEL_NAMESPACE", "federation-signals")
C2_URL = os.environ.get("SIGNALS_C2_URL", "http://127.0.0.1:50561")
GPU_KEY = "federation.zndx.org/gpu"
ADMIT_TIMEOUT_S = float(os.environ.get("HERMES_YK_GPU_ADMIT_TIMEOUT_S", "600"))
LEASE_DIR = Path(os.environ.get("ZNDX_GPU_LEASE_DIR", "/tmp/zndx-gpu-leases"))


def _kubeconfig_env() -> dict[str, str]:
    env = os.environ.copy()
    env["KUBECONFIG"] = str(Path.home() / ".config/kube/rke2.yaml")
    return env


def application_yaml(
    workload_id: str = WORKLOAD_ID,
    *,
    queue: str = QUEUE,
    resource_class: str = RESOURCE_CLASS,
    gpu_tokens: int = GPU_TOKENS,
) -> str:
    gpu_req = f'\n          {GPU_KEY}: "{gpu_tokens}"' if gpu_tokens else ""
    gpu_lim = f'\n          {GPU_KEY}: "{gpu_tokens}"' if gpu_tokens else ""
    return f"""apiVersion: v1
kind: Pod
metadata:
  name: {workload_id}
  namespace: {NAMESPACE}
  labels:
    app.kubernetes.io/component: minifi-sentinel
    federation.project: hermes
    federation.workload_id: {workload_id}
    federation.resource_class: {resource_class}
    federation.kind: agent-rtc
    federation.phase: listen
    applicationId: {workload_id}
    queue: {queue}
    zarf.dev/agent: ignore
  annotations:
    zarf.dev/agent: ignore
    yunikorn.apache.org/app-id: {workload_id}
    yunikorn.apache.org/queue: {queue}
    federation.zndx.org/envelope: "apps=1,gpu={gpu_tokens},mem=16Mi,cpu=10m"
    federation.zndx.org/phase: "listen"
spec:
  restartPolicy: Never
  priorityClassName: {PRIORITY_CLASS}
  hostNetwork: true
  containers:
    - name: sentinel
      image: rancher/mirrored-pause:3.6
      imagePullPolicy: IfNotPresent
      env:
        - name: FEDERATION_PROJECT
          value: hermes
        - name: FEDERATION_RESOURCE_CLASS
          value: {resource_class}
      lifecycle:
        preStop:
          exec:
            command:
              - sh
              - -c
              - |
                wget -q -O- --post-data='{{"workload_id":"{workload_id}","project":"hermes","phase":"preempted","sentinel_id":"{workload_id}"}}' \\
                  --header='Content-Type: application/json' \\
                  "{C2_URL}/c2-protocol/last-gasp" || true
      resources:
        requests:
          cpu: 10m
          memory: 16Mi{gpu_req}
        limits:
          cpu: 10m
          memory: 16Mi{gpu_lim}
"""


def cerebras_thinking_yaml() -> str:
    return application_yaml(
        CEREBRAS_WORKLOAD_ID,
        queue=CEREBRAS_QUEUE,
        resource_class=CEREBRAS_CLASS,
        gpu_tokens=0,
    ).replace("federation.kind: agent-rtc", "federation.kind: cerebras-thinking").replace(
        'federation.zndx.org/phase: "listen"',
        'federation.zndx.org/phase: "think"',
    )


def _kubectl(args: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess:
    kubectl = shutil.which("kubectl")
    if kubectl is None:
        raise RuntimeError("kubectl not on PATH — agent-rtc sentinel cannot admit")
    return subprocess.run(
        [kubectl, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_kubeconfig_env(),
        check=False,
    )


def apply_manifest(raw: str) -> None:
    kubectl = shutil.which("kubectl")
    if kubectl is None:
        raise RuntimeError("kubectl not on PATH — agent-rtc sentinel cannot admit")
    proc = subprocess.run(
        [kubectl, "-n", NAMESPACE, "apply", "-f", "-"],
        input=raw,
        capture_output=True,
        text=True,
        timeout=30,
        env=_kubeconfig_env(),
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"YK sentinel apply failed: {(proc.stderr or proc.stdout).strip()}"
        )


def apply_sentinel(workload_id: str = WORKLOAD_ID) -> None:
    apply_manifest(application_yaml(workload_id))
    log.info("applied sentinel %s on %s", workload_id, QUEUE)


def apply_cerebras_thinking() -> None:
    apply_manifest(cerebras_thinking_yaml())
    log.info("applied sentinel %s on %s", CEREBRAS_WORKLOAD_ID, CEREBRAS_QUEUE)


def wait_admitted(workload_id: str = WORKLOAD_ID, timeout_s: float = ADMIT_TIMEOUT_S) -> None:
    deadline = time.monotonic() + timeout_s
    last = ""
    while time.monotonic() < deadline:
        proc = _kubectl(
            [
                "-n",
                NAMESPACE,
                "get",
                "pod",
                workload_id,
                "-o",
                "jsonpath={.status.phase}",
            ]
        )
        last = (proc.stdout or "").strip()
        if last == "Running":
            log.info("YK admitted %s", workload_id)
            return
        if last in {"Failed", "Succeeded"}:
            raise RuntimeError(f"YK sentinel {workload_id} phase={last}")
        time.sleep(2)
    raise RuntimeError(
        f"YK did not admit {workload_id} on {QUEUE} within {timeout_s:.0f}s "
        f"(last phase={last or 'unknown'}). agent-rtc is unavailable."
    )


def delete_sentinel(workload_id: str = WORKLOAD_ID) -> None:
    _kubectl(
        [
            "-n",
            NAMESPACE,
            "delete",
            "pod",
            workload_id,
            "--ignore-not-found=true",
            "--wait=false",
        ]
    )


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


def admit() -> None:
    apply_sentinel()
    wait_admitted()


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


def release() -> None:
    release_gpu_lease()
    delete_sentinel()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in {"admit", "release"}:
        print("usage: python -m hsengine.engine.yk_sentinel admit|release", file=sys.stderr)
        return 2
    if args[0] == "admit":
        admit()
        return 0
    release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
