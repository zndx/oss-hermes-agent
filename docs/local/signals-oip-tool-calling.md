# Spec: federated tool calling on OIP (and what already exists)

**For:** `zndx/signals-protocol` (OIP LLM tensor profile) and lattice engines
(Gaius first — it already serves native `tool_calls` on Complete). Hermes
(`rch/devenv`) is the first *agent* peer that needs the model to emit
OpenAI-shaped calls while Hermes executes tools locally.

Not applied this session — pick up in the protocol tree, then Gaius OIP,
then Hermes client.

## What is true today

OIP as specified in `specification/protocol/oip_mandatory.md` is a **text
LLM tensor profile**:

| tensor | direction |
|--------|-----------|
| `prompt`, `system_prompt` | in |
| `completion`, `reasoning` (+ `*_delta` on stream) | out |

Parameters: `max_tokens`, `temperature`, capability/model hints. No
`tools[]`, no `messages[]`, no `tool_calls`. Gaius `ModelInfer` and Hermes
`oip_client` / `oip_servicer` implement exactly that: prompt → text.

**Tool calling already lives on `zndx.engine.v1.Complete`**, not OIP:

- Request: `tools_json`, `tool_choice`, `messages_json` (fields 9–11)
- Response: `repeated ToolCall tool_calls`, `finish_reason=tool_calls`
- Gaius `ZndxEngineServicer.Complete` forwards tools to vLLM
  (`--enable-auto-tool-choice` / `qwen3_coder` parser) and returns
  structured `ToolCall`s. Method capabilities (`cot_reasoning`, …) are
  `INVALID_ARGUMENT` when combined with tools (`#EP.00000020.NOMIX`).

Hermes does **not** send those fields. `hsengine` `Complete` / OIP /
`complete_on_peer` only pass `prompt` + `system_prompt` + `json_schema`.
`CompleteResult` has no `tool_calls`. Even the deprecated Complete path
cannot drive a Hermes tool loop today.

KServe OIP itself has no chat/tools messages. KServe’s *generative* face
is a separate OpenAI HTTP `/v1/chat/completions`. That is not the lattice
lingua franca (`oip_mandatory.md`: Complete and product HTTP must lower
to OIP; peer-private model HTTP is DENY).

## Two product shapes (do not mix)

1. **Hermes as agent client of a lattice model.** Hermes owns tools
   (terminal, files, …). Gaius/Ægir own GPUs. Each agent turn is: send
   tools + messages → get `tool_calls` or final text → Hermes executes →
   append tool results → repeat. This **requires** tools on the portable
   inference face.
2. **Hermes as opaque `capability=agent`.** A peer sends a goal; Hermes
   runs its own loop and returns the answer. Tools never leave Hermes.
   OIP text in/out is enough. That is a valid inbound shape and keeps
   the core waist narrow, but it does **not** let lattice `thinking`
   drive Hermes tools.

The gap the waffle join does not close is (1).

## Options

### A — Extend the zndx LLM tensor profile (recommended protocol work)

Additive **convention** on existing OIP messages. Do not fork
`open_inference_grpc.proto`. Advertise
`ServerMetadata.extensions += ["llm_tools_v1"]`.

| name | where | payload |
|------|--------|---------|
| `tools` | input tensor BYTES | OpenAI `tools[]` JSON |
| `messages` | input tensor BYTES | OpenAI `messages[]` JSON (tool loop) |
| `tool_choice` | `parameters` string | `auto` / `required` / `none` / named-tool JSON |
| `tool_calls` | output tensor BYTES | JSON array of `{id,name,arguments}` matching `ToolCall` |
| `finish_reason` | `parameters` string | already used by Hermes OIP (`stop` / `tool_calls` / `length`) |

`ModelStreamInfer`: optional `tool_calls_delta` BYTES frames, prefix-stable
like draft text. Finalize still carries the full `tool_calls` tensor.

**CIS / plain KServe:** unknown extra inputs often `INVALID_ARGUMENT`.
Send `tools`/`messages` **only** to peers whose `ServerMetadata.extensions`
includes `llm_tools_v1`. Unary CIS stays the text profile. Matches the
existing proxy rule (vanilla OIP peer must still work).

Complete remains a local façade that **lowers** to these tensors (the
deprecation already requires that). Field JSON is the same as
`tools_json` / `messages_json` / `ToolCall`.

### B — Parameters-only (no new tensors)

Stuff `tools_json` / `messages_json` / `tool_calls_json` into
`InferParameter.string_param`. Same CIS-gating via extensions. Worse
shape: OIP parameters are scalars; a multi-turn `messages[]` is not.
Reject unless A is blocked.

### C — Dual-face bridge (near-term Hermes only)

Hermes tool loops call **Complete** (Gaius already implements it).
Text-only / CIS hops stay on OIP. Honest about deprecations.md: Complete
is not the portable path. Acceptable as a **Hermes client** slice while
A lands on Gaius OIP, not as the long-term contract.

Hermes still has to wire `tools_json` / `messages_json` / `tool_calls`
on Complete — that work is needed for A’s façade anyway.

### D — Opaque agent only (no model-side tools on the wire)

Inbound `capability=agent` returns final text. No protocol change. Does
not satisfy “Hermes tools driven by federated `thinking`.”

### E — OpenAI HTTP on the engine (reject)

KServe generative `/v1/chat/completions` with tools. Second face, extra
port, fights OIP-mandatory and “no peer-private model HTTP.”

### F — New `Engine/Chat` RPC (reject)

Duplicates Complete. Grows the waist. Complete already has the messages.

## Hermes plugins (perihelion)

Do **not** grow core (`run_agent.py`, toolsets). Three stock plugin kinds:

| Kind | Location | Seam |
|------|----------|------|
| Model | `hsengine/plugins/signals_oip` + bundled shim `plugins/model-providers/signals` | `ProviderProfile.create_client` → OpenAI-shaped client; OIP `llm_tools_v1` else Complete |
| Memory | `hsengine/plugins/signals_memory` installed to `$HERMES_HOME/plugins/signals-memory` | `MemoryProvider` (`sync_turn`, `prefetch`, `on_pre_compress`). **Not** under repo `plugins/memory/` (that set is closed). |
| Compaction | `hsengine/plugins/signals_compact` + bundled shim `plugins/context_engine/signals` | `ContextEngine` named `signals` (`context.engine: signals`). Subclasses `ContextCompressor` in v1. |

Activate: `model.provider: signals`, `memory.provider: signals`, `context.engine: signals`.
`python -m hsengine.plugins.install` (devenv enterShell) copies memory into the profile home.

## Recommendation

| horizon | work |
|---------|------|
| Protocol | **A** in `oip_mandatory.md` + `llm_tools_v1` extension string |
| Gaius | OIP `ModelInfer`/`ModelStreamInfer` accept `tools`/`messages`, reuse the Complete vLLM extra_body path, emit `tool_calls` tensor; `ServerMetadata.extensions` |
| Hermes client | Prefer OIP when the peer advertises `llm_tools_v1`; else Complete (C) until Gaius OIP catches up. Thread tools through `complete` / `CompleteResult` |
| Inbound Hermes | Keep **D** as the default for foreign Complete/OIP callers (`agent` = opaque). Do not dump the Hermes tool schema onto every lattice Complete |

Constraints to keep:

- Tools + method capabilities stay NOMIX.
- `tools` and `json_schema` stay mutually exclusive (`#GR.00000010`).
- Empty `tools` tensor is text-only (honest). Do not invent a prompt-side
  tool roster — Gaius already learned that the vLLM parser **discards**
  `<tool_call>` when `tools[]` is absent.
- No Atlas / extra store; tool results stay in `messages[]` on the next
  infer. Lineage remains OpenLineage RunEvents if a turn is recorded.

## Accept (after A + Gaius OIP)

```bash
# peer advertises the extension
grpcurl -plaintext 127.0.0.1:50051 inference.GRPCInferenceService/ServerMetadata
# extensions include llm_tools_v1

# ModelInfer with tools tensor → finish_reason=tool_calls + tool_calls output
# (same Qwen tool_calls Gaius Complete already returns)
```

Hermes agent turn against Gaius `thinking` then executes the named tools
locally and sends `messages` (assistant tool_calls + tool results) on the
next OIP infer.
