# signals-protocol

The shared wire contracts of the **zndx signals federation** — the protocols by which
sibling projects' engines (Gaius, Ægir, Atelier, Metabase, Synth, …) invoke each other
and **transparently proxy plain KServe Open Inference Protocol peers** (including
Cloudera Inference Service).

## Hard requirement (all adopters)

**Every signals-protocol engine implementation MUST adopt full-duplex OIP:**

| Obligation | Detail |
|------------|--------|
| OIP **server** face | `inference.GRPCInferenceService` — health, metadata, `ModelInfer`, **`ModelStreamInfer`** |
| OIP **client** proxy | Call plain KServe/CIS with **only** OIP — no project-private RPCs on that hop |
| Unary transparency | Unary-only OIP peers (CIS) remain first-class |
| Full duplex | Bidi `ModelStreamInfer` on the engine face for interactive / multi-frame turns |
| Deprecation | Vestigial alternatives marked `DEPRECATED` in code and docs — see below |

Normative text: [`specification/protocol/oip_mandatory.md`](specification/protocol/oip_mandatory.md).

Project-native streams (Gaius TUI streams, Metabase product HTTP, etc.) may remain for
**local product UX** only. They are **not** federation.

## Why this exists

Measured 2026-07-03: per-project engines mirrored message *shapes*, but gRPC method
paths embed package+service, so foreign stubs got `UNIMPLEMENTED`. Each engine
registers shared faces **additionally** beside native services.

OIP is the **lingua franca** for heterogeneous serving (KServe, Triton, CIS, vLLM-OIP).
`zndx.engine.v1` remains a capability/remediation **convenience** face that **lowers to
OIP** — not a parallel federation.

## Protocols

| package | path | status |
|---|---|---|
| **`inference` (KServe OIP v2 + full-duplex)** | [`proto/inference/v2/`](proto/inference/v2/) · [oip_mandatory.md](specification/protocol/oip_mandatory.md) | **MANDATORY** federation face |
| `zndx.engine.v1` | [`specification/protocol/engine_grpc.md`](specification/protocol/engine_grpc.md) | v1 — `Complete` (**deprecated as sole path**; lowers to OIP) + `Status` (+ `surfaces[]`, [`surfaces.md`](specification/protocol/surfaces.md)) + `ServerQuery` + `Remediate` + **`Yield`**; capability vocabulary in [`capabilities.md`](specification/protocol/capabilities.md); warehouse `tx_id` is RFC 9562 UUIDv7 ([`tx_id.md`](specification/protocol/tx_id.md)); data products on shared RustFS ([`data_products.md`](specification/protocol/data_products.md)) |
| `zndx.scheduler.v1` | [`specification/protocol/scheduler_grpc.md`](specification/protocol/scheduler_grpc.md) | v1 — federated **scheduler** capability (queues, policy, projection, **queue-share requests**). Lab backend: YuniKorn; not a vendor in the service name |
| `zndx.verify.v1` | — | RESERVED: verification artifacts on the wire (reasoner certificates, kvasir proof DAGs — the rase_types direction from Gaius) |

Deprecations ledger: [`specification/protocol/deprecations.md`](specification/protocol/deprecations.md).

## Operations (identity, secrets, process coordination)

Wire protocols alone are not enough to use **Signals core services** or to
coordinate multi-engine host work. Adopters must follow:

| Document | Purpose |
|---|---|
| [`specification/operations/kerberos_and_secretspec.md`](specification/operations/kerberos_and_secretspec.md) | **Binding** Kerberos principal catalog, SecretSpec allowlists, `kinit` process wrappers, Ranger onboarding |
| [`specification/operations/minifi_sentinels.md`](specification/operations/minifi_sentinels.md) | **Binding design** — MiNiFi C++ sentinels (C2 + OTel); **Knative Serving** scale-to-zero + **YuniKorn** admission on RKE2 |

**Reference implementation:** [weathership/signals](https://github.com/weathership/signals) is the first federation project on Kerberos + SecretSpec, and vendors **MiNiFi C++** (`components/minifi-cpp`) and **YuniKorn core** (`components/yunikorn-core`) for sentinel coordination. Sibling engines should implement these procedures—do not invent a parallel long-term identity or process-control path.

## Adopters (must implement OIP full duplex)

| project | native service | shared faces | gRPC (typical) |
|---|---|---|---|
| signals | `zndx.scheduler.v1.Scheduler` (platform) | OIP + `zndx.engine.v1.Engine` | :50551 (lab lattice) |
| gaius | `gaius.engine.GaiusService` (see `gaius FEDERATION.md`) | OIP + `zndx.engine.v1.Engine` | :50051 |
| aegir | `aegir.engine.AegirEngine` | OIP + `zndx.engine.v1.Engine` | :50151 |
| atelier | `atelier.engine.AtelierEngine` | OIP + `zndx.engine.v1.Engine` | :50251 |
| synth | project native | OIP + `zndx.engine.v1.Engine` | :50351 |
| metabase | `metabase.engine.MetabaseEngine` (capability `dashboard`) | OIP + `zndx.engine.v1.Engine` | :50451 |
| hermes-agent | ACP / plugins | planned (client of core + engines) | — |

GPU co-tenancy rides the shared advisory lease dir `/tmp/zndx-gpu-leases` (per-GPU-set
lock files, project-tagged owners) plus each engine's authoritative nvidia-smi probe.
Cross-project **admission** is YuniKorn (sentinel **is** the Application).
**Yield** is C2 HTTP → `Engine/Yield` gRPC. See
[`specification/operations/minifi_sentinels.md`](specification/operations/minifi_sentinels.md).

## Evolution rules

- **Additive-only within a version**: new fields get new numbers; nothing renamed/removed. Breaking changes → new versioned package.
- **OIP first for portable inference**: new inference features land on OIP tensors/parameters or additive OIP extensions, then optional Complete facade.
- **Capabilities, not models** on the convenience face: `Complete.capability` names abilities; engines resolve to backends or peer `model_name`.
- **Engine-private details stay private**: internal vLLM ports, log paths, product streams do not replace OIP.
- Changes land **here** first, then submodule bump in each adopter.

## Vestigial alternatives (must mark deprecated)

Do **not** treat these as complete federation:

- Unary-only `Complete` without OIP server/proxy
- Product loopback HTTP complete as the cross-process inference API
- Gaius-native streams as peer-facing protocol
- Direct peer vLLM HTTP ports

Mark in code:

```text
// DEPRECATED(federation): use OIP ModelInfer / ModelStreamInfer.
// Local facade / transitional adapter only. See signals-protocol deprecations.md
```

## Codegen

```bash
# OIP (mandatory face)
python -m grpc_tools.protoc -Iproto \
  --python_out=<dst> --grpc_python_out=<dst> \
  proto/inference/v2/open_inference_grpc.proto

# Capability convenience face
python -m grpc_tools.protoc -Iproto \
  --python_out=<dst> --grpc_python_out=<dst> \
  proto/zndx/engine/v1/engine.proto
```

Generated code is vendored per-project; **this repo is the single source of truth**.
