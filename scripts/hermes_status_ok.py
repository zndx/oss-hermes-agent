#!/usr/bin/env python3
"""Lattice accept probe: Engine/Status must answer project=hermes.

Thin on purpose — do not import hsengine.engine.server (that pulls the daemon).
Used by devenv readiness and systemd start wrappers.
"""
from __future__ import annotations

import os
import sys

import grpc

from hsengine.engine.generated.zndx.engine.v1 import engine_pb2 as zpb
from hsengine.engine.generated.zndx.engine.v1 import engine_pb2_grpc as zpb_grpc

TARGET = os.environ.get("HERMES_ENGINE_TARGET", "127.0.0.1:50651")
WANT = "hermes"


def main() -> int:
    try:
        with grpc.insecure_channel(TARGET) as ch:
            stub = zpb_grpc.EngineStub(ch)
            st = stub.Status(zpb.StatusRequest(), timeout=2)
    except Exception as e:
        print(f"UNAVAILABLE {TARGET}: {e}", file=sys.stderr)
        return 1
    project = (st.project or "").strip().lower()
    if project != WANT:
        print(f"WRONG_PROJECT {TARGET}: {st.project!r} != {WANT!r}", file=sys.stderr)
        return 1
    caps = [ep.capability for ep in st.endpoints]
    print(f"ok project={st.project} capabilities={caps} surfaces={len(st.surfaces)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
