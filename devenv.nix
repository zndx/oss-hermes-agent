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
    venv.enable = true;

    uv = {
      enable = true;
      sync = {
        enable = true;
        # `all` covers every extra except `matrix` (upstream python-olm is
        # broken) and the `rl` / `yc-bench` git deps. It includes `dev`, so
        # pytest is available too.
        extras = [ "all" ];
        # devenv defaults to `--no-install-workspace`, which syncs the
        # dependencies but skips hermes-agent itself — no `hermes` on PATH.
        arguments = [ "--frozen" ];
      };
    };
  };

  # https://devenv.sh/packages/
  #
  # Binaries the agent shells out to at runtime (mirrors nix/packages.nix),
  # plus portaudio for the `voice` extra's sounddevice bindings.
  packages = with pkgs; [
    git
    nodejs_20
    ripgrep
    openssh
    ffmpeg
    portaudio
  ];

  # https://devenv.sh/basics/
  env = {
    # Use the nixpkgs interpreter above; never let uv fetch its own CPython.
    UV_PYTHON_DOWNLOADS = "never";
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
    echo "  pytest tests/ -q       test suite"
    echo "  hermes-browser-tools   optional: npm browser tooling"
  '';

  # https://devenv.sh/tests/
  enterTest = ''
    hermes version
    python -c "import hermes_cli, run_agent"
  '';

  # See full reference at https://devenv.sh/reference/options/
}
