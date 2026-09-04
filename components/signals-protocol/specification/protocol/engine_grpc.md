# zndx.engine.v1 — gRPC protocol specification

## Service

`zndx.engine.v1.Engine` — registered by every signals engine **additionally**, beside
its native project service and beside the **mandatory** OIP
`inference.GRPCInferenceService` face.

Insecure channels on the local fabric today; mTLS engine-to-engine when the
federation identity layer lands (per Gaius FEDERATION.md).

> **Federation lingua franca is OIP.**  
> See [oip_mandatory.md](oip_mandatory.md). This package is a **capability /
> remediation convenience face**, not a substitute for KServe Open Inference
> Protocol. Engines that only implement `Complete` are **not** fully federated.

## Complete

> **DEPRECATED as the sole cross-engine inference path.**  
> Implementations MUST lower `Complete` to OIP `ModelInfer` (and stream via
> `ModelStreamInfer` when serving interactive clients). Plain KServe / CIS peers
> speak OIP, not `Complete`.

Request an inference **capability**. The engine resolves the capability to a model
it manages (or to an OIP `model_name` on a peer) and serves the request; the caller
of *this* RPC never addresses a model endpoint. OIP callers use `model_name` on
`ModelInfer` instead.

| field | semantics |
|---|---|
| `capability` | names an ability ("instruct", "metabot", "dashboard"); empty = engine default |
| `prompt`, `system_prompt` | chat-style; map to OIP tensors `prompt` / `system_prompt` |
| `max_tokens` | generous defaults recommended — reasoning models trace verbosely; `finish_reason: "length"` signals truncation |
| `temperature` | sampling temperature |
| `json_schema` | optional JSON Schema (string) → engine-enforced structured output (e.g. vLLM guided-json); empty = unconstrained |
| `timezone` | optional IANA zone of the *caller* (e.g. `America/Denver`). Empty = unspecified. |
| `clock_json` | optional JSON Clock (today / tomorrow / `tomorrow_morning` as UTC instants). Empty = none. |
| `capabilities` | a capability SET the engine must satisfy TOGETHER: ≤1 **method** capability (an optillm technique class, e.g. `cot_reasoning`) + ≤1 **model** capability (e.g. `thinking`). Unsatisfiable mix → FAILED_PRECONDITION `#EP.00000020.NOMIX` listing offered models × methods. Empty = the legacy single `capability`. Vocabulary: [capabilities.md](capabilities.md). (added 2026-08-30) |

Response: `text` (the answer; reasoning inline when not separated), `model` (what
actually served), token counts, `latency_ms`, `reasoning_content` (separated
chain-of-thought when the model/parser splits it — retained, never dropped: thinking
traces are corpus value-adds in this federation), `finish_reason` (`stop` | `length`).
On `capabilities[]` requests, additionally `reasoning[]` — every reasoning layer the
fulfilment produced, each a `ReasoningLayer{layer: model|method, producer, text,
tokens}` (model layer first when present) — and `fulfilled_by` (e.g.
`cot_reflection@engine/Qwen3.8-27B@vllm:8081`). A method that cannot recover the
model layer keeps the method layer and the serving engine logs
`#EP.00000021.METHODTRACE`. (added 2026-08-30)

OIP lowering: `text` maps from the OIP `completion` tensor and `reasoning_content`
from the OIP `reasoning` tensor (see [oip_mandatory.md](oip_mandatory.md)).

Errors surface as gRPC status codes; the engine stays up (INTERNAL for serving
failures, UNAVAILABLE while a capability is cold-loading if the engine chooses not
to block).

## Yield

C2 → engine only. The Signals-owned C2 server (gRPC client) calls `Yield` on
the owning lattice engine after a sentinel last-gasp or missed heartbeat.
The engine ends the **local process** that `workload_id` names (the process
the engine started). Idempotent: unknown `workload_id` returns `ok=true`,
`process_ended=false`.

| field | semantics |
|---|---|
| `workload_id` | Shared key with the YK Application / C2 agent / OTel |
| `reason` | `PREEMPTED` (YK ended the sentinel), `COMPLETED`, `ORPHAN`, `UNIT_STOP` |
| `sentinel_id` | MiNiFi agent id when known |
| `detail` | Optional human note |

Not inference (`Complete`). Not ontology (`Remediate`). Not a Gaius-native
RPC. Sentinels never dial gRPC.

## Warehouse `tx_id` (UUIDv7)

Data-product `tx_id` / details `t` **MUST** be [RFC 9562](https://www.rfc-editor.org/rfc/rfc9562.html)
UUID **version 7**. Implementations **SHOULD** utilize v7 over v1 and v6
(RFC 9562 §4). Canonical string form is required on the wire.

The Signals warehouse **does not store** a non-v7 id. It raises a boundary
signal to the **source** engine so that engine remints and resubmits:

| field | value |
|---|---|
| `SignalKind` | `TX_ID_NOT_UUIDV7` (5) |
| `offending` | the rejected `tx_id` |
| `subject` | `product_id` when known |
| `authority` | `RFC 9562 §5.7` |
| `capability` | `reauthor` (or the source's remint capability) |

`Remediate` stays with the **source** (peer). Signals does not invent a
replacement id for a foreign tx; it refuses the row and surfaces the signal.

Kudu range expiry uses `epoch_hour` (derived from the UUIDv7 timestamp
when present), week-wide tablets, settle after 4 weeks. `tx_id` is identity
+ datalog order, not the tablet bound.

Peer products on shared RustFS: [`data_products.md`](data_products.md).

## ServerQuery

Pairwise **server-to-server query** (Matrix Server-Server *Queries*). Not
epidemic gossip. Not CZMQ zgossip. Older engines: `UNIMPLEMENTED`.

| kind | payload |
|------|---------|
| `REMOTES` | named git remotes + advertised `head` |
| `SCHEDULES` | pg_cron / Airflow hints |
| `PEERS` | configured lattice Engine targets |
| `NOTE` | one FedWiki page (`WikiNote`) |
| `SURFACES` | this engine's advertised `Surface` list |
| `QUEUES` | `QueueHint[]` — **declared leaf shape** (path, max, default guarantee). Time-varying occupancy floors are `zndx.scheduler.v1.Scheduler/RequestQueueShare`, not this snapshot. Peers never call scheduler-backend REST. |
| `WORKLOADS` | `WorkloadHint[]` — WRK `model`, `capabilities`, `tensor_parallel` / `pipeline_parallel`, `gpu_tokens`. Never encode those in the queue name; pick heavy/medium/light (or extract/compute) from `gpu_tokens`. |

Do not invent remotes, peers, or UI URLs. Empty is honest.

## Status

The federation-facing view: `project`, per-capability `Endpoint`
(capability, model, healthy, `gpu_ids`), `total_gpus`, and `surfaces[]`
(`kind`, `url`, `healthy`). `kind=primary` is the product UI a waffle
lists. Empty `surfaces` means this engine advertises none. Engine-private
details (internal vLLM ports, log paths) stay absent.

See [`surfaces.md`](surfaces.md) for the peer implementation note.

Does **not** replace OIP `ServerLive` / `ServerReady` / `ModelReady`. Peers that
need standard KServe probes use OIP health RPCs.

## Remediate

Boundary-signal remediation (Holland CAS). Engine-local adaptive inference; the
caller’s membrane disposes the correction. Not a substitute for OIP.

## RecordLineage

Additive v1. Peers persist OpenLineage `RunEvent` JSON on **Signals Atlas**
(`POST /api/v1/lineage`). They MUST NOT keep a private lineage catalog.

`LineageRequest.event_json` is the RunEvent. `event_type` must match
`event_json.eventType` when both are set (`START` | `COMPLETE` | `FAIL`).
`LineageResponse.accepted` is true only after Atlas accepts the event.

## How the specification is consumed

**The `.proto` files are the specification** (same stance as
[OIP inference_grpc](https://github.com/kserve/open-inference-protocol/blob/main/specification/protocol/inference_grpc.md)).
Implementations **code-generate** stubs/clients from those protos. First-party
tooling (lattice CI, unit start probes, peer clients) **SHOULD** use generated
bindings — that is implementing the protocol properly.

| Consumer | Preferred mechanism |
|----------|---------------------|
| Engines / our scripts / libraries | **Codegen** from `proto/` (committed or build-step) |
| External operators / ad-hoc tooling | **gRPC server reflection** so bare `grpcurl` works |

Reflection does **not** replace the proto; it exposes the live service so tools
that do not ship our tree can still call `zndx.engine.v1.Engine` without local
descriptor flags.

## Server reflection (required on lattice ports)

Every engine that exposes `zndx.engine.v1.Engine` on the federation lattice
**MUST** enable [gRPC server reflection](https://github.com/grpc/grpc/blob/master/doc/server-reflection.md)
on that same listen port and advertise at least:

- `zndx.engine.v1.Engine`
- `grpc.reflection.v1alpha.ServerReflection` (or the reflection service name
  your stack registers)

| Requirement | Detail |
|-------------|--------|
| Python engines | depend on `grpcio-reflection` (or equivalent) and enable reflection at server start |
| External accept | bare `grpcurl -plaintext <host>:<port> zndx.engine.v1.Engine/Status` succeeds |
| First-party CI | generated-stub Status client **and** reflection check |

`grpcurl -proto …` against a live engine is fine for debugging, but first-party
automation should prefer **generated clients** from the same protos engines use.

## Co-tenancy conventions (informative)

Engines share hosts and GPUs. Advisory lease dir `/tmp/zndx-gpu-leases`;
authoritative check is nvidia-smi. Foreign resident capabilities are respected —
forward OIP (or Complete→OIP) rather than moving GPUs.

## OIP mapping (normative)

| zndx.engine.v1 | Open Inference Protocol |
|---|---|
| `Complete` (deprecated as sole path) | **MUST** lower to `ModelInfer`; interactive paths **MUST** use `ModelStreamInfer` where applicable |
| `Status` | complements `ServerMetadata` / `ModelReady` (capability+GPU view) |
| capability names | resolved by the engine to local backend or peer `model_name` |

Full rules: [oip_mandatory.md](oip_mandatory.md). Deprecations: [deprecations.md](deprecations.md).
