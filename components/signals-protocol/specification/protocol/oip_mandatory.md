# KServe Open Inference Protocol — mandatory federation face

**Status:** NORMATIVE for all signals-protocol engine adopters  
**Package:** `inference` (`proto/inference/v2/open_inference_grpc.proto`)  
**Adopters:** Gaius · Ægir · Atelier · Metabase (`mbengine`) · Synth · any future engine

## Hard requirement

Every implementation that registers as a **signals federation engine** MUST:

1. **Serve** the OIP `GRPCInferenceService` face (health, metadata, inference).
2. **Client-proxy** plain KServe OIP peers (including Cloudera Inference Service)
   without requiring peer-specific extension RPCs.
3. **Implement full-duplex streaming** via `ModelStreamInfer` on the engine face
   (bi-directional stream of `ModelInferRequest` / `ModelInferResponse`).
4. **Preserve transparency:** a vanilla OIP peer that only speaks unary
   `ModelInfer` must still work end-to-end through the engine’s proxy path.

Chat convenience (`zndx.engine.v1.Complete`), ACP harnesses, Metabot tools,
Gaius-native streams, and product loopback HTTP are **not** the federation
lingua franca. They may exist only as local facades that **lower to OIP**.

## Required RPCs (server face)

| RPC | Arity | Notes |
|-----|--------|--------|
| `ServerLive` | unary | liveness |
| `ServerReady` | unary | readiness |
| `ModelReady` | unary | per-model readiness |
| `ServerMetadata` | unary | declare extensions (include full-duplex when ready) |
| `ModelMetadata` | unary | shapes / datatypes |
| `ModelInfer` | unary | **required** — CIS / plain KServe compatibility |
| `ModelStreamInfer` | **bidi stream** | **required on signals engines** (see proto comment) |

## LLM tensor profile (zndx convention)

Text LLMs map onto OIP tensors so chat facades and CIS stay interoperable:

| Tensor name | Direction | datatype | contents |
|-------------|-----------|----------|----------|
| `prompt` | input | BYTES | UTF-8 user/prompt body |
| `system_prompt` | input (optional) | BYTES | UTF-8 system preamble |
| `completion` | output | BYTES | UTF-8 completion text |
| `reasoning` | output (optional) | BYTES | chain-of-thought when separated |

Parameters (temperature, max_tokens, capability→model routing hints) ride
`ModelInferRequest.parameters` / per-input parameters as string or int64 values.
Capability names from `zndx.engine.v1` resolve **inside the engine** to a local
backend or to an OIP `model_name` on a peer — never as a requirement on CIS.

## Proxy rules

When `protocol = kserve` (or equivalent) for a peer:

| Rule | Behaviour |
|------|-----------|
| MUST | Use OIP only — no Gaius/Metabase/Ægir private RPCs on the wire to that peer |
| MUST | Map failures to gRPC status codes OIP clients understand |
| MUST | Support unary `ModelInfer` to unary-only peers (CIS) |
| MUST | Prefer `ModelStreamInfer` when both ends advertise it |
| MUST NOT | Drop reasoning / partials when the backend provides them |
| SHOULD | Surface stream frames promptly (no full-buffer before first byte) |

## Full duplex and interactive agents

Interactive product agents (Metabot, Gaius MetaAgent, etc.) need incremental
text and thinking. On a signals engine:

```
product UI stream  ←→  engine  ←→  ModelStreamInfer (peer engine)
                              ←→  ModelInfer (unary CIS, adapted)
                              ←→  local ACP / vLLM (still expose OIP face)
```

Product SSE/AISDK is a **local presentation**; the **portable** stream is OIP.

## Relationship to `zndx.engine.v1.Complete`

| Surface | Role |
|---------|------|
| OIP `ModelInfer` / `ModelStreamInfer` | **Mandatory** federation + CIS path |
| `zndx.engine.v1.Complete` | **Deprecated as sole federation path** — convenience facade that MUST lower to OIP tensors |
| `zndx.engine.v1.Status` | Still useful for capability/GPU lease visibility; does not replace OIP health |

See [deprecations.md](deprecations.md).

## Adopter checklist

- [ ] OIP server registered on the engine gRPC port (or documented dual-port with discovery)
- [ ] OIP client can call a plain KServe/CIS endpoint (unary green)
- [ ] `ModelStreamInfer` implemented on the engine; interop test with another signals engine
- [ ] Unary-only peer proxy tested (buffer/adapt path)
- [ ] Project-native streams documented as non-federation
- [ ] Docs and code mark vestigial alternatives `DEPRECATED`
