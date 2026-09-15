# hsengine lives in signals-plugins

The lattice engine / AgentRTC sidecar is packaged as **`signals-hsengine`**
in `$SIGNALS_PLUGINS` (default `~/local/src/wxs/signals-plugins`).

```bash
uv add --optional signals --editable "$SIGNALS_PLUGINS"
# devenv uv sync --extra signals --frozen then installs from the lock.
python -m hsengine    # hermes-engine
```

Listen UI stays a Hermes plugin (`signals-listen`). This checkout does
**not** vendor `hsengine/`. The sidecar is lock-owned via
`[tool.uv.sources] signals-hsengine` and the `signals` extra — do not
`uv pip install -e` (a stray pip install can drop the editable and the
next exact sync will not put it back).

Hermes core patches that remain should stay **generic**:

- `agent.session_runtime` (plugins/extras register overlays)
- dashboard `tab.position: "after:chat"` (plugin nav pin)
- HTTPS join URL bootstrap for getUserMedia plugin tabs
