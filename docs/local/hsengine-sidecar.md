# hsengine lives in signals-plugins

The lattice engine / AgentRTC sidecar is packaged as **`signals-hsengine`**
in `~/local/src/wxs/signals-plugins` (`pip install -e .`, console script
`hermes-engine`). Listen UI stays a Hermes plugin (`signals-listen`).

This checkout still vendors `hsengine/` so the devenv engine process keeps
running until we drop the tree and install the extra from `SIGNALS_PLUGINS`
instead (same venv cannot load two `hsengine` packages).

Hermes core patches that remain should stay **generic**:

- `agent.session_runtime` + entry point `hermes_agent.session_runtime`
- dashboard `tab.position: "after:chat"` (plugin nav pin)
- HTTPS join URL bootstrap for getUserMedia plugin tabs
