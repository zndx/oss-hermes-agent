# Hermes systemd units

**Membership is the system unit** `hermes.service` under `signals.target`
(`signals/infra/systemd/hermes.service` → ExecStart
`scripts/systemd_start.sh`). A user unit on `default.target` is not a
peer of the group: after a host reboot `signals.target` comes up and
Hermes stays down.

```bash
# From the Signals checkout (sudo):
just install-systemd --peers hermes --enable
sudo systemctl start hermes.service
```

Nautilus is a **resident** under `devenv up -d` plus an optional hourly
tick timer (user):

```bash
# user units (tick only — not the engine)
mkdir -p ~/.config/systemd/user
ln -sf ~/local/src/oss/hermes-agent/scripts/systemd/hermes-nautilus-tick.service ~/.config/systemd/user/
ln -sf ~/local/src/oss/hermes-agent/scripts/systemd/hermes-nautilus-tick.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now hermes-nautilus-tick.timer
```

The tick is idempotent. If the resident is down it fails loudly
(`#NT.00000009.TICKSKIP`); a missed hour is `unknown`, never replayed.
