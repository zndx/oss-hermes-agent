# hsengine lives in signals-plugins

The lattice engine / AgentRTC sidecar is packaged as **`signals-hsengine`**
in `$SIGNALS_PLUGINS` (default `~/local/src/wxs/signals-plugins`).

```bash
uv pip install -e "$SIGNALS_PLUGINS"
# or: ~/local/src/wxs/signals-plugins/scripts/install.sh --engine
python -m hsengine    # hermes-engine
```

Listen UI stays a Hermes plugin (`signals-listen`). This checkout does
**not** vendor `hsengine/`. devenv installs the extra editable (`--inexact`
so `uv sync --frozen` does not uninstall it).

Hermes core patches that remain should stay **generic**:

- `agent.session_runtime` (plugins/extras register overlays)
- dashboard `tab.position: "after:chat"` (plugin nav pin)
- HTTPS join URL bootstrap for getUserMedia plugin tabs
