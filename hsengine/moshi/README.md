# agent-rtc: Kyutai STT for Hermes WebRTC captions

YK leaf: `root.internal.inference.agent-rtc` (dash is valid; see
`root.external.rate-metered`). **1 GPU guaranteed**, 1 application.

The devenv `moshi` process is a **supervisor** (control `:5081`) that is
resident with Hermes. CUDA `moshi-server` (`:5080`) and the YK claims
start on WebRTC Connect and stop on the last Disconnect:

1. Yield local Gaius thinking (`gaius-thinking`, 4×4090).
2. Stamp `hermes-cerebras-thinking` on `root.external.subscription.rate-limited`.
3. Admit `hermes-agent-rtc` (`zndx-gpu-high`) and start moshi-server.
4. Hermes Complete for `agent`/`thinking` uses Cerebras `qwen-3.8-27b`.

Disconnect reverts: stop moshi-server, release both sentinels. Gaius
`thinking-ready` may restore local Qwen.

The Listen tab burns **user** speech onto the outbound video. That is
**Kyutai STT** (`stt-1b-en_fr`) served by **moshi-server** (Rust/Candle)
after YuniKorn admits the `hermes-agent-rtc` sentinel.

There is no whisper/CPU path. If YK does not admit, moshi-server is
missing, or no GPU can be leased, agent-rtc is unavailable.

Moshi 7B dialogue is a different module on this same stack: its text
stream is the assistant inner monologue, not a transcript of the mic.

Sentinel: `federation.zndx.org/gpu: 1` only — never `nvidia.com/gpu` on
the pause pod. Host CUDA runs after admit + `/tmp/zndx-gpu-leases`.
