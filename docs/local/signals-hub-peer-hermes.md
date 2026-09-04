# Spec: list Hermes on the Signals hub Federated menu

**For:** `wxs/signals` (peer contract / hub PEERS) and optionally Gaius
`surface_title`. **Not applied this session** — pick up in those trees.

Hermes (this checkout, `rch/devenv`) already:

- Serves `zndx.engine.v1.Engine` on **`:50651`** (`Status.project=hermes`,
  capability `agent`).
- Advertises `Status.surfaces` `kind=primary` →
  `http://tinybox.dev.vista.zndx.org:9119` (WARP / Zero Trust name; never
  loopback).
- Answers `ServerQuery` `SURFACES` / `PEERS`.
- Runs the product dashboard on `0.0.0.0:9119` (LAN `192.168.1.55` + WARP)
  with secretspec basic auth.

Launchers (Gaius waffle, Signals UI) **do not** hard-code peer UI URLs.
They seed `SIGNALS_ENGINE_TARGET` (`:50551`), `Engine/Status` each target,
and one-hop `ServerQuery PEERS`. Hermes therefore appears in the Federated
menu only after the **hub roster** includes `:50651`.

## Signals (`~/local/src/wxs/signals`)

`config/platform/peer-contract.json`:

1. `engine_grpc_lattice` — add `"hermes": 50651` next to `metabase: 50451`.
   `configured_peers()` already emits every integer port in that map except
   self / skip keys. That is what `ServerQuery PEERS` on `:50551` returns.

2. `peers[]` — add an external peer object (same shape as Metabase):

```json
{
  "id": "hermes",
  "capability": "agent",
  "project_status": "hermes",
  "grpc_port": 50651,
  "dashboard_http": "http://tinybox.dev.vista.zndx.org:9119",
  "license": "MIT",
  "external": true,
  "path_hint": "~/local/src/oss/hermes-agent",
  "unit": "hermes.service",
  "after": ["signals-ready.service"],
  "architecture_class": "license_external_isolated",
  "notes": [
    "OSS Hermes Agent — lattice engine hsengine + dashboard :9119",
    "WorkingDirectory the hermes checkout; scripts/systemd_start.sh",
    "Do not vendor Hermes into the ASL2 signals tree"
  ]
}
```

3. Recycle `signals-engine` so PEERS picks up the contract. Accept:

```bash
grpcurl -plaintext 127.0.0.1:50551 zndx.engine.v1.Engine/ServerQuery \
  -d '{"kind":"SERVER_QUERY_KIND_PEERS"}'
# expect project=hermes target=…:50651
```

4. Optional systemd sample: `just install-systemd --peers hermes` once a
   unit wrapper exists (Hermes already has `scripts/systemd_start.sh`).

Tests that freeze the lattice map (`tests/signals/test_engine_s2s.py` and
any peer-contract fixtures) need `hermes: 50651`.

## Gaius (optional)

`gaius.engine.s2s.surface_title` known-dict can add `"hermes": "Hermes"`.
Today `.title()` already yields `Hermes`. Discovery does **not** need a
Gaius `federation.peers` row if the Signals hub lists Hermes: Gaius seeds
`SIGNALS_ENGINE_TARGET` then walks PEERS.

## Metabase

Metabase does **not** render a Federated launcher (one-way discovery). The
menu lives in Gaius / Signals UI. No Metabase code change is required for
Hermes to appear there.

## Accept (after hub roster)

From a WARP or LAN browser, the waffle item **Hermes** opens
`http://tinybox.dev.vista.zndx.org:9119`. Engine/Status on `:50651` shows
`surfaces[kind=primary].healthy=true` once `processes.dashboard` is up.
