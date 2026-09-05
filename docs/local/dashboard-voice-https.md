# Dashboard voice: Synth listen now, engine-local WebRTC later

Do **not** put WebRTC on `signals-protocol`. Engines that need media
implement it **locally** (Hermes `hsengine`, Synth `Observe`). The
federated engine is the join; the media plane is per-project.

## What Synth already shipped (copy this)

Browser **listen** (not PortAudio on the server):

1. **Secure context** — devenv `services.caddy` with `tls internal`,
   `local_certs`, `default_sni 192.168.1.55`, named hosts including the
   LAN IP. `:8392` TLS → gateway `:8391`. WebKit (iPad) has no HTTP
   exception; click-through or trust the local CA once.
2. **Capture** — `ui/src/lib/micCapture.ts`: `getUserMedia` (music-safe
   constraints) → AudioWorklet → PCM16LE 16 kHz → `wss://…/ws/observe`.
3. **Engine RPC (Synth proto, not zndx.engine.v1)** —
   `Observe.ObserveAudio(stream AudioChunk)` with `pcm16` + `sample_rate`.
   Gateway WS is a thin bridge: first JSON `{"sample_rate":N}`, then
   binary frames.

WebRTC is a later, still **engine-local**, upgrade (Opus/RTCPeerConnection
on the same project engine). signals-protocol stays Complete/OIP/Status.

## What Hermes does today (why the laptop is silent)

Chat is `hermes --tui` over a PTY. `/voice` → `voice.record` → PortAudio
on tinybox. `web/` has no `getUserMedia`. Desktop already records in
Chromium (`use-mic-recorder.ts`). GitHub #20765 / #54352.

bwrap does not bind `/dev/snd` — correct; the mic is the laptop.

## Hermes plan (same layers as Synth)

| Layer | Hermes | Notes |
|-------|--------|--------|
| TLS | devenv `services.caddy` `:9120` → dashboard `:9119` | LAN IP-SAN + tinybox names; click-through OK. WARP hostname can terminate TLS at the edge and proxy here or to loopback `:9119`. |
| Listen (now) | dashboard `getUserMedia` → `wss://…/ws/voice` → **hsengine** stream | PCM16 like Synth. STT on the engine (not PortAudio). |
| WebRTC (later) | hsengine-local PeerConnection | Direct to this engine, advertised however we already advertise the engine (`Status` / surfaces), **not** a new signals-protocol RPC. |
| STT | existing `stt.provider` | Groq/OpenAI/local whisper once audio arrives. |

`HERMES_DASHBOARD_PUBLIC_URL` must match the **browser origin**
(`https://192.168.1.55:9120` or `https://tinybox.dev.vista.zndx.org`)
so cookies and WS stay on the secure context. Caddy (loopback) is an
already-trusted proxy for `X-Forwarded-Proto`.

## Origins

| Origin | Secure? |
|--------|---------|
| `http://127.0.0.1:9119` | yes (loopback) |
| `http://192.168.1.55:9119` | no |
| `https://192.168.1.55:9120` (caddy, click-through) | yes |
| `https://tinybox.dev.vista.zndx.org` (WARP TLS) | yes |

## Do not

- Add `Observe` / WebRTC to `zndx.engine.v1` / signals-protocol.
- Record on the server and hope PulseAudio/SSH forwards the laptop.
- Mix `https://` pages with `http://` API/WS.
