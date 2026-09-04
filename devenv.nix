{ pkgs, lib, config, inputs, ... }:

{
  # https://devenv.sh/languages/
  #
  # Hermes targets Python 3.11+ and is locked with uv. `uv sync` installs the
  # workspace itself in editable mode, which is what puts `hermes`,
  # `hermes-agent` and `hermes-acp` on PATH pointing at this checkout.
  languages.python = {
    enable = true;
    package = pkgs.python311;
    # Canonical local venv: $DEVENV_STATE/venv (.devenv/state/venv).
    # Do not use a uv-downloaded .venv (UV_PYTHON_DOWNLOADS=never).
    venv.enable = true;

    uv = {
      enable = true;
      sync = {
        enable = true;
        # Perihelion: core Hermes + Signals-owned extras only (see
        # hsengine.surface.LOCAL_EXTRAS). Never `[all]`, never upstream
        # extras/plugins. Expand LOCAL_EXTRAS when the lattice grows.
        extras = [ "signals" ];
        allExtras = false;
        # devenv defaults to `--no-install-workspace`, which syncs the
        # dependencies but skips hermes-agent itself — no `hermes` on PATH.
        arguments = [ "--frozen" ];
      };
    };
  };

  # https://devenv.sh/languages/javascript/
  # Dashboard + ui-tui require Node ^22.22 (package.json engines). Do not
  # put nodejs_* in packages — devenv owns the runtime and npm on PATH.
  # npm.install.enable stays off: the workspace includes Electron desktop.
  languages.javascript = {
    enable = true;
    package = pkgs.nodejs_22;
    npm.enable = true;
  };

  # https://devenv.sh/packages/
  #
  # Binaries the agent shells out to at runtime (mirrors nix/packages.nix),
  # plus portaudio for the `voice` extra's sounddevice bindings.
  packages = with pkgs; [
    git
    ripgrep
    openssh
    ffmpeg
    portaudio
    grpcurl
  ] ++ lib.optional (pkgs ? secretspec) pkgs.secretspec;

  # Gitignored `.env` is the secretspec dotenv store (dashboard auth).
  dotenv.enable = true;

  # https://devenv.sh/basics/
  env = {
    # Use the nixpkgs interpreter above; never let uv fetch its own CPython.
    UV_PYTHON_DOWNLOADS = "never";
    SIGNALS_ENGINE_TARGET = "127.0.0.1:50551";
    HERMES_ENGINE_TARGET = "127.0.0.1:50651";
  };

  # Lattice engine — join as project=hermes, capability=agent on :50651.
  # Readiness is Engine/Status (same accept gate as gaius/metabase).
  processes.engine = {
    exec = ''
      cd ${config.devenv.root}
      export HERMES_ADVERTISE_HOST="''${HERMES_ADVERTISE_HOST:-''${SIGNALS_ADVERTISE_HOST:-tinybox.dev.vista.zndx.org}}"
      # Nix profile PYTHONPATH must not leak into the engine (Gaius doctrine).
      export PYTHONPATH=""
      exec ${config.devenv.root}/.devenv/state/venv/bin/python -m hsengine
    '';
    process-compose = {
      readiness_probe = {
        exec.command = ''
          ${config.devenv.root}/.devenv/state/venv/bin/python ${config.devenv.root}/scripts/hermes_status_ok.py \
            || grpcurl -plaintext -max-time 2 127.0.0.1:50651 zndx.engine.v1.Engine/Status
        '';
        initial_delay_seconds = 2;
        period_seconds = 5;
        timeout_seconds = 4;
        success_threshold = 1;
        failure_threshold = 36;
      };
    };
  };

  # Product dashboard — LAN 0.0.0.0:9119 + WARP hostname in public_url.
  # Auth gate is mandatory off-loopback (secretspec password).
  processes.dashboard = {
    exec = ''
      cd ${config.devenv.root}
      export HERMES_ADVERTISE_HOST="''${HERMES_ADVERTISE_HOST:-''${SIGNALS_ADVERTISE_HOST:-tinybox.dev.vista.zndx.org}}"
      exec ${config.devenv.root}/scripts/processes/hermes-dashboard.sh
    '';
    process-compose = {
      readiness_probe = {
        exec.command = ''
          ${config.devenv.root}/.devenv/state/venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9119/api/health', timeout=3)"
        '';
        initial_delay_seconds = 15;
        period_seconds = 10;
        timeout_seconds = 5;
        success_threshold = 1;
        failure_threshold = 60;
      };
    };
  };

  # https://devenv.sh/scripts/
  #
  # Browser tools are optional and pull a large browser bundle, so this stays
  # opt-in rather than running on every shell entry.
  scripts.hermes-browser-tools.exec = ''
    cd "${config.devenv.root}" && npm install
  '';

  # Keep this cheap: `hermes version` imports the whole CLI and runs an update
  # check, which is not worth paying for on every shell entry.
  enterShell = ''
    echo "Hermes Agent dev shell (python $(python --version | cut -d' ' -f2))"
    echo "  hermes                 interactive CLI"
    echo "  hermes version         version / environment info"
    echo "  python -m hsengine     signals lattice engine (:50651, project=hermes)"
    echo "  hermes dashboard       web UI :9119 (LAN + WARP; secretspec auth)"
    echo "  node/npm               $(node --version 2>/dev/null || echo missing) / $(npm --version 2>/dev/null || echo missing)"
    echo "  venv                   ${config.devenv.state}/venv  (devenv:python:uv)"
    echo "  pytest tests/ -q       test suite"
    echo "  hermes-browser-tools   optional: npm browser tooling"
    _sp="$HOME/local/src/wxs/signals-plugins/scripts/install.sh"
    if [ -x "$_sp" ]; then "$_sp" --quiet || true; fi
  '';

  # https://devenv.sh/tests/
  enterTest = ''
    hermes version
    python -c "import hermes_cli, run_agent, hsengine"
    python ${config.devenv.root}/tests/engine/test_surface_extras.py
    python ${config.devenv.root}/tests/engine/test_dashboard_process.py
  '';

  # See full reference at https://devenv.sh/reference/options/
}
