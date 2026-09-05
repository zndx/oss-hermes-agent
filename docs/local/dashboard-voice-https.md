# Dashboard voice from a laptop: HTTPS is necessary, not sufficient

The Chat tab **embeds `hermes --tui` over a PTY**. `/voice` and the record
key call `voice.record` → PortAudio/`sounddevice` on **tinybox**, not the
browser. A laptop on WARP or LAN cannot donate its microphone to that
path. GitHub #20765 / #54352.

Desktop already captures in Chromium via `getUserMedia` + `MediaRecorder`
(`apps/desktop/src/app/chat/composer/hooks/use-mic-recorder.ts`). The
`web/` dashboard has **no** `getUserMedia` usage.

## Two gates

### 1. Secure context (HTTPS)

Browsers allow `navigator.mediaDevices.getUserMedia` only in a
[secure context](https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts):
`https://` or `http://localhost` / `http://127.0.0.1`.

| Origin | Secure? |
|--------|---------|
| `http://127.0.0.1:9119` | yes (loopback exception) |
| `http://192.168.1.55:9119` | **no** |
| `http://tinybox.dev.vista.zndx.org:9119` | **no** |
| `https://tinybox.dev.vista.zndx.org` (TLS at the edge) | yes |
| `https://192.168.1.55:…` with click-through | yes (exception accepted) |

Hermes uvicorn has **no** `--ssl-certfile` today. TLS is meant to terminate
in front (docs: Tailscale Serve / reverse proxy → `http://127.0.0.1:9119`).

**WARP / Zero Trust hostname**

1. Terminate TLS on the WARP/Cloudflare name (tunnel or ingress), proxy to
   `http://127.0.0.1:9119`.
2. `HERMES_DASHBOARD_PUBLIC_URL=https://tinybox.dev.vista.zndx.org` (no
   `:9119` if 443 is the public port).
3. `dashboard.trusted_proxies` = the proxy’s IP so `X-Forwarded-Proto:
   https` is honoured (Secure cookies). Loopback proxies are already
   trusted.

**LAN IP click-through**

Self-signed or mkcert on a second port (e.g. `:9120`):

```bash
openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
  -keyout /raid/build/hermes/tls/lan.key \
  -out /raid/build/hermes/tls/lan.crt \
  -subj "/CN=192.168.1.55" \
  -addext "subjectAltName=IP:192.168.1.55,DNS:tinybox.lan"
```

Then either Caddy/nginx `https://192.168.1.55:9120` → `:9119`, or teach
uvicorn `ssl_certfile`/`ssl_keyfile` (not wired yet). The browser warning
is enough: after “Advanced → proceed”, it **is** a secure context.

Do not mix `https://warp-host` pages with `http://192.168.x` API/WS.

### 2. Capture in the browser (the missing product)

HTTPS without a browser recorder still talks to tinybox’s (likely empty)
mic, and the bwrap jail does not bind `/dev/snd`.

Needed:

1. Dashboard Chat (or a sidecar next to the PTY) uses the desktop
   `use-mic-recorder` pattern: `getUserMedia` → `MediaRecorder` → upload
   or WS chunks.
2. Gateway accepts that audio and runs STT (`voice.transcribe` / existing
   STT providers) instead of PortAudio `start_continuous`.
3. STT must actually be configured (`stt.provider`, local whisper or
   Groq/OpenAI). Perihelion extras do **not** include `[voice]`; PortAudio
   is on the host for the CLI, not for the laptop.

## Suggested order

1. Put HTTPS on the WARP name (proxy + `public_url` + `trusted_proxies`).
2. Optional LAN: self-signed/mkcert click-through on a TLS port.
3. Port desktop mic capture into `web/` (the real voice fix).
4. Only then worry about `[voice]` / whisper on the server for STT.

Do not chroot/`bwrap` `/dev/snd` as a substitute — that still records the
wrong machine.
