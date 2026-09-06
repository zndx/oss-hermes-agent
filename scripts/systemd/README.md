# Hermes systemd units

Symmetric with Gaius: `hermes.service` is the devenv control plane;
Nautilus is a **resident** under `devenv up -d` plus an hourly tick timer.

```bash
# user units
mkdir -p ~/.config/systemd/user
ln -sf ~/local/src/oss/hermes-agent/scripts/systemd/hermes.service ~/.config/systemd/user/
ln -sf ~/local/src/oss/hermes-agent/scripts/systemd/hermes-nautilus-tick.service ~/.config/systemd/user/
ln -sf ~/local/src/oss/hermes-agent/scripts/systemd/hermes-nautilus-tick.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now hermes.service
systemctl --user enable --now hermes-nautilus-tick.timer
```

The tick is idempotent. If the resident is down it fails loudly
(`#NT.00000009.TICKSKIP`); a missed hour is `unknown`, never replayed.
