# Deprecations — vestigial federation alternatives

**Policy:** Full-duplex OIP is mandatory for every signals-protocol engine.
Anything that previously served as a substitute federation or inference face
must be marked deprecated in **code and docs** until removed.

## Deprecated as federation / portable inference

| Vestige | Was used for | Replacement | Status |
|---------|--------------|-------------|--------|
| Unary-only `zndx.engine.v1.Complete` as the **only** cross-engine path | Chat between engines | OIP `ModelInfer` + `ModelStreamInfer`; Complete becomes a local facade that lowers to OIP | **DEPRECATED** (facade may remain) |
| Product loopback HTTP complete (e.g. Metabase `:50462` `/v1/complete`) as long-term IPC | JVM without grpc-java | Prefer gRPC OIP or streaming product IPC that mirrors OIP frames | **DEPRECATED** for federation; loopback OK only as transitional local adapter |
| Project-native streams as federation (Gaius `InitStream`, `SwarmStream`, `MetaAgentQueryStream`, …) | TUI/MCP product UX | Keep for product; **not** federation. Peers must not depend on them | **DEPRECATED as federation** |
| Embedding ACP / agent harness in the product (Metabase-in-JVM ACP) | Agent sessions | ACP stays engine-local; product is signals/OIP only | **REJECTED** (already policy) |
| Peer-private vLLM HTTP ports as federation | Direct model ports | OIP (or Complete facade → OIP) only | **DEPRECATED / DENY** |
| “Horizon only” OIP language in older READMEs | Future CIS | OIP is **now** mandatory, not horizon | **SUPERSEDED** |

## Still allowed (not federation)

| Surface | Allowed when |
|---------|----------------|
| `zndx.engine.v1.Complete` | Local/product convenience; MUST lower to OIP; MUST NOT be the only way peers reach you |
| `zndx.engine.v1.Remediate` | Boundary adaptation (engine-local capability); not a substitute for OIP |
| `zndx.engine.v1.Status` | Capability/GPU lease visibility alongside OIP health |
| Gaius product streams | TUI/MCP only; document `// PRODUCT-ONLY — not federation` |
| Metabase product HTTP | Transitional loopback; document `// DEPRECATED federation; local adapter` |
| ACP (Grok/Vibe) | Engine-local agent host; expose results via OIP/stream to products |

## Marking standard (all adopters)

**Code**

```text
// DEPRECATED(federation): use OIP ModelInfer / ModelStreamInfer.
// This path remains as a local facade / transitional adapter only.
// Removal tracked: signals-protocol deprecations.md
```

**Docs**

- Call out **DEPRECATED** in the first paragraph of any page that describes the old path.
- Link to `specification/protocol/oip_mandatory.md`.
- Do not describe Complete-only peers as “fully federated.”

## Adopter tracking

| Project | OIP server | OIP client proxy | ModelStreamInfer | Vestiges marked |
|---------|------------|------------------|------------------|-----------------|
| Gaius | partial (private proto) | documented | TBD | TBD |
| Ægir | TBD | TBD | TBD | TBD |
| Atelier | TBD | TBD | TBD | TBD |
| Metabase / mbengine | **yes** (ref) | **yes** (client + peer fallback) | **yes** (ref) | marked |
| Synth | TBD | TBD | TBD | TBD |

Update this table as engines adopt; green means green tests against a plain OIP peer (unary) and a signals peer (stream).
