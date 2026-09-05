{ pkgs, lib, config, inputs, ... }:

let
  # Lab default matches synth/vigil (/raid/build/<project>/data). Override
  # with RUSTFS_DATA_DIR in .env. builtins.getEnv — not config.env — so
  # extraEnvironment cannot recurse.
  rustfsDataDir =
    let v = builtins.getEnv "RUSTFS_DATA_DIR";
    in if v != "" then v else "/raid/build/hermes/data";

  rustfsBuckets = [
    "hermes-artifacts"
    "hermes-sessions"
  ];

  # Nix OpenSSH is built without GSSAPI; Ubuntu /etc/ssh/ssh_config still
  # has `GSSAPIAuthentication yes` (line 53) so every `git push` warns.
  # Prefer the user config, then the system file with GSSAPI* stripped.
  sshNoGssapi = pkgs.writeShellScriptBin "ssh" ''
    set -euo pipefail
    state="''${DEVENV_STATE:-/tmp}/ssh-nongss"
    mkdir -p "$state"
    cfg="$state/config"
    {
      if [[ -f "''${HOME}/.ssh/config" ]]; then
        echo "Include ''${HOME}/.ssh/config"
      fi
      grep -viE '^[[:space:]]*GSSAPI' /etc/ssh/ssh_config 2>/dev/null || true
    } > "$cfg"
    exec ${lib.getExe pkgs.openssh} -F "$cfg" "$@"
  '';
  opensshForPath = pkgs.symlinkJoin {
    name = "openssh-devenv";
    paths = [ sshNoGssapi pkgs.openssh ];
    ignoreCollisions = true;
  };

  # Port lattice: synth 9000/9001 · signals 9010/9011 · hermes 9020/9021.
  mc = pkgs.writeShellScriptBin "mc" ''
    set -euo pipefail
    CLIENT_DIR="''${RUSTFS_CLIENT_CONFIG_DIR:-$DEVENV_STATE/rustfs/mc}"
    mkdir -p "$CLIENT_DIR"
    ADDRESS="''${RUSTFS_ADDRESS:-127.0.0.1:9020}"
    ACCESS="''${RUSTFS_ACCESS_KEY:-rustfsadmin}"
    SECRET="''${RUSTFS_SECRET_KEY:-rustfsadmin}"
    ${pkgs.minio-client}/bin/mc --config-dir "$CLIENT_DIR" \
      alias set local "http://$ADDRESS" "$ACCESS" "$SECRET" \
      --api S3v4 --path on >/dev/null 2>&1 || true
    exec ${pkgs.minio-client}/bin/mc --config-dir "$CLIENT_DIR" "$@"
  '';
in
{
  overlays = [
    (final: prev: {
      rustfs = inputs.rustfs.packages.${prev.stdenv.system}.default;
    })
  ];

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
    gh
    git
    ripgrep
    opensshForPath
    ffmpeg
    portaudio
    grpcurl
    bubblewrap # jail engine+dashboard (scripts/lib/hermes-bwrap.sh)
    mc # wrapped alias `local` against the devenv rustfs service
  ] ++ lib.optional (pkgs ? secretspec) pkgs.secretspec;

  # Gitignored `.env` is the secretspec dotenv store (dashboard auth).
  dotenv.enable = true;

  # https://devenv.sh/basics/
  env = {
    # Use the nixpkgs interpreter above; never let uv fetch its own CPython.
    UV_PYTHON_DOWNLOADS = "never";
    SIGNALS_ENGINE_TARGET = "127.0.0.1:50551";
    HERMES_ENGINE_TARGET = "127.0.0.1:50651";
    # Files UI stays inside this checkout (not $HOME).
    HERMES_DASHBOARD_FILES_ROOT = config.devenv.root;
    RUSTFS_DATA_DIR = rustfsDataDir;
    RUSTFS_CLIENT_CONFIG_DIR = config.env.DEVENV_STATE + "/rustfs/mc";
  };

  # TLS front for LAN/WARP browsers (getUserMedia needs a secure context).
  # Same shape as synth: caddy internal CA, no :80 redirect, default_sni for
  # no-SNI IP clients. :9120 tls → dashboard :9119. Click-through is enough
  # for a laptop; iPad WebKit wants the CA trusted once.
  services.caddy = {
    enable = true;
    ca = null;
    config = ''
      {
        local_certs
        auto_https disable_redirects
        default_sni 192.168.1.55
      }
      localhost:9120, 127.0.0.1:9120, 192.168.1.55:9120, tinybox:9120, tinybox.lan:9120, tinybox.dev.vista.zndx.org:9120 {
        tls internal
        reverse_proxy 127.0.0.1:9119
      }
    '';
  };

  # https://devenv.sh/services/rustfs/ — native service (ports, env, /health).
  # Overlay pin in devenv.yaml matches Signals/synth; package comes from pkgs.rustfs.
  # Port lattice: synth 9000/9001 · signals 9010/9011 · hermes 9020/9021.
  services.rustfs = {
    enable = true;
    package = pkgs.rustfs;
    bind = "127.0.0.1";
    port = 9020;
    consolePort = 9021;
    accessKey = "rustfsadmin";
    secretKey = "rustfsadmin";
    extraEnvironment = {
      RUSTFS_DATA_DIR = rustfsDataDir;
    };
  };

  tasks."devenv:rustfs:buckets" = {
    exec = lib.concatStringsSep "\n" (
      map (b: ''mkdir -p "${rustfsDataDir}/${b}"'') rustfsBuckets
    );
    before = [ "devenv:processes:rustfs" ];
  };

  # Lattice engine — join as project=hermes, capability=agent on :50651.
  # Readiness is Engine/Status (same accept gate as gaius/metabase).
  processes.engine = {
    exec = ''
      cd ${config.devenv.root}
      export HERMES_ADVERTISE_HOST="''${HERMES_ADVERTISE_HOST:-''${SIGNALS_ADVERTISE_HOST:-tinybox.dev.vista.zndx.org}}"
      # Nix profile PYTHONPATH must not leak into the engine (Gaius doctrine).
      export PYTHONPATH=""
      exec ${config.devenv.root}/scripts/processes/hermes-engine.sh
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
    echo "  hermes dashboard       web UI :9119 HTTP / :9120 HTTPS (caddy local CA; getUserMedia)"
    echo "  rustfs                 S3 :9020 / console :9021  (mc alias local; $RUSTFS_DATA_DIR)"
    echo "  bwrap                  engine+dashboard jail (HOME=/home/hermes; HERMES_BWRAP=0 to skip)"
    echo "  node/npm               $(node --version 2>/dev/null || echo missing) / $(npm --version 2>/dev/null || echo missing)"
    echo "  venv                   ${config.devenv.state}/venv  (devenv:python:uv)"
    echo "  pytest tests/ -q       test suite"
    echo "  hermes-browser-tools   optional: npm browser tooling"
    ${config.devenv.root}/scripts/devenv-enter-checks.sh || true
  '';

  # https://devenv.sh/tests/
  enterTest = ''
    hermes version
    python -c "import hermes_cli, run_agent, hsengine"
    python ${config.devenv.root}/tests/engine/test_surface_extras.py
    python ${config.devenv.root}/tests/engine/test_dashboard_process.py
    bash -n ${config.devenv.root}/scripts/devenv-enter-checks.sh
    bash -n ${config.devenv.root}/scripts/merge-upstream.sh
    bash -n ${config.devenv.root}/scripts/dashboard-curl.sh
    bash -n ${config.devenv.root}/scripts/lib/hermes-bwrap.sh
    bash -n ${config.devenv.root}/scripts/processes/hermes-engine.sh
    bash -n ${config.devenv.root}/scripts/processes/hermes-dashboard.sh
  '';

  # See full reference at https://devenv.sh/reference/options/
}
