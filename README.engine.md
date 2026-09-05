# hsengine — Hermes as a signals `agent` peer

Local gRPC coordination engine that presents this Hermes checkout to the
[zndx signals federation](components/signals-protocol/README.md). Patterned
after Metabase (`mbengine`, an external non-Signals project) for the lattice
face; Nautilus instance follows Gaius (read-only adoption only).

| claim | value |
|---|---|
| project (`Status.project`) | `hermes` |
| capability | **`agent`** |
| gRPC | `:50651` (native `hermes.engine` + `zndx.engine.v1.Engine` + OIP) |
| advertised UI (`Status.surfaces`) | `http://tinybox.dev.vista.zndx.org:9119` (`HERMES_ADVERTISE_HOST` / `HERMES_PRIMARY_UI`) |
| dashboard bind | `0.0.0.0:9119` (LAN `192.168.1.55` + WARP; basic auth via secretspec) |
| federation peers | gaius `:50051` (`thinking`) · aegir `:50151` (`instruct`) |
| Nautilus instance | `config/supervision/hermes.textproto` (observe-only; Gaius leads the supervisor) |
| Object store | Hermes RustFS S3 `:9020` / console `:9021` (`/raid/build/hermes/data`; buckets `hermes-artifacts`, `hermes-sessions`). Overlay pin matches Signals/synth. Lattice peers keep their own: synth `:9000`, Signals `:9010`. |

This tree is an **external** peer. Do not vendor Hermes into Signals. A
sample systemd unit (when Signals adds `--peers hermes`) should
`WorkingDirectory=` here.

## Remotes

| remote | URL | push |
|--------|-----|------|
| `origin` | `git@github.com:zndx/oss-hermes-agent.git` | yes (our fork) |
| `upstream` | `git@github.com:NousResearch/hermes-agent.git` | **no** (`DISABLE`) |

NousResearch is high velocity. Fetch `upstream/main` often and merge into
the published fork (`rch/devenv` is the working line; `origin/main` is
protected and lags until a PR).

```bash
./scripts/merge-upstream.sh          # how far behind
./scripts/merge-upstream.sh --merge  # merge upstream/main into HEAD
git push origin HEAD
```

`devenv` `enterShell` runs `scripts/devenv-enter-checks.sh` (network at most
once an hour): install missing `signals-plugins` from GitHub, notice when
trunk moved, and notice when `HEAD` is behind `upstream/main`.

## Operational surface (perihelion)

The local venv is core upstream Hermes plus **Signals-owned extras only**.
The Signals stack may grow extras (`hsengine.surface.LOCAL_EXTRAS`, today
`signals` = lattice engine + Nautilus). Do **not** sync upstream Hermes extras (`[all]`, `web`,
`google`, `youtube`, `mcp`, messaging, …) or activate in-tree plugins /
`optional-skills` to make the agent “complete.” Hold that line as the
lattice evolves. `tests/engine/test_surface_extras.py` is the tripwire.

## Quick start

```bash
# Canonical venv is devenv-managed: .devenv/state/venv (not a uv-downloaded .venv).
devenv tasks run devenv:python:uv    # uv sync --frozen --extra signals
./scripts/compile_engine_protos.sh   # after proto edits
python -m hsengine                   # or: devenv up  (engine + dashboard)
python scripts/hermes_status_ok.py   # accept: Engine/Status project=hermes
secretspec set HERMES_DASHBOARD_BASIC_AUTH_PASSWORD
devenv up                            # :50651 engine + :9119 dashboard
```

The Federated menu **is** `Engine/Status.surfaces` (`kind=primary`). Hermes
sends that and **joins** by `Engine/Announce` to directory seeds
(`SIGNALS_ENGINE_TARGET` and `federation.peers`, typically Ægir `:50151`).
Launchers stay pull-only: they walk `ServerQuery PEERS` then Status.
`UNIMPLEMENTED` on a seed is honest. Spec:
[`docs/local/signals-hub-peer-hermes.md`](docs/local/signals-hub-peer-hermes.md).

Accept probes:

```bash
grpcurl -plaintext 127.0.0.1:50651 zndx.engine.v1.Engine/Status
grpcurl -plaintext -d '{"kind":"SERVER_QUERY_KIND_SURFACES"}' \
  127.0.0.1:50651 zndx.engine.v1.Engine/ServerQuery
grpcurl -plaintext -d '{"kind":"SERVER_QUERY_KIND_PEERS"}' \
  127.0.0.1:50651 zndx.engine.v1.Engine/ServerQuery
```

## Faces on `:50651`

| service | role |
|---|---|
| `zndx.engine.v1.Engine` | lattice join (`Status`, `ServerQuery`, `Complete`, `Yield`, `RecordLineage`, `WatchWorkload`) |
| `inference.GRPCInferenceService` | mandatory KServe OIP (unary + bidi `ModelStreamInfer`) |
| `hermes.engine.HermesEngine` | native status / instance probe |
| gRPC reflection | required so bare `grpcurl` works |

`Complete` is **DEPRECATED as the sole federation path**. Hermes does not
host GPU models; `agent` / `instruct` federate to peer `thinking` /
`instruct` (OIP when the peer reports the model ready). Reasoning traces
are retained. `Remediate` is Ægir's. Lineage POSTs to Signals Atlas.

`ServerQuery` answers `SURFACES`, `PEERS`, `REMOTES`, and `SOURCE_POSTURE`.
Other kinds return an honest empty payload.

## Nautilus (follow Gaius)

Gaius leads the supervisor implementation. Hermes ships only the
**instance**:

```bash
./scripts/nautilus-validate.sh
```

Restart strategies are `NONE` (observe / score / escalate — never
actuate) until the external Nautilus binary earns promotion. Do not add
an in-engine Nautilus daemon.

## Layout

```
components/signals-protocol/     # vendored proto + specs (OIP + engine + supervision)
config/base.conf                 # HOCON single source of truth
config/supervision/hermes.textproto
hsengine/engine/                 # gRPC daemon
scripts/compile_engine_protos.sh
scripts/hermes_status_ok.py
```
