{ lib, pkgs, hermesAgent, ... }:

let
  system = pkgs.stdenv.hostPlatform.system;
  hermesPackages = hermesAgent.packages.${system};

  # Hermes' PM artifacts are upstream Linux binaries rather than conventional
  # Nix packages. Copy and patch them so they use NixOS' dynamic linker and
  # expose stable commands on PATH.
  cuaDriver = pkgs.stdenvNoCC.mkDerivation {
    pname = "hermes-cua-driver";
    version = "0.21.0";
    src = hermesPackages.pm-cua-driver;
    nativeBuildInputs = [ pkgs.autoPatchelfHook ];
    buildInputs = [
      pkgs.libxkbcommon
      pkgs.libx11
      pkgs.libxi
      pkgs.stdenv.cc.cc.lib
    ];
    dontUnpack = true;
    installPhase = ''
      runHook preInstall
      mkdir -p "$out/libexec/cua-driver" "$out/bin"
      cp -a "$src"/. "$out/libexec/cua-driver/"
      ln -s "$out/libexec/cua-driver/cua-driver" "$out/bin/cua-driver"
      runHook postInstall
    '';
  };

  agentBrowser = pkgs.stdenvNoCC.mkDerivation {
    pname = "hermes-agent-browser";
    version = "0.26.0";
    src = hermesPackages.pm-agent-browser;
    nativeBuildInputs = [ pkgs.autoPatchelfHook ];
    buildInputs = [ pkgs.stdenv.cc.cc.lib ];
    dontUnpack = true;
    installPhase = ''
      runHook preInstall
      mkdir -p "$out/libexec/agent-browser" "$out/bin"
      cp -a "$src"/package/. "$out/libexec/agent-browser/"
      chmod +x "$out/libexec/agent-browser/bin/agent-browser-linux-x64"
      ln -s "$out/libexec/agent-browser/bin/agent-browser-linux-x64" "$out/bin/agent-browser"
      runHook postInstall
    '';
  };
in
{
  imports = [ hermesAgent.homeManagerModules.default ];

  home = {
    username = "max";
    homeDirectory = "/home/max";
    stateVersion = "26.05";
  };

  programs.home-manager.enable = true;
  programs.hermes-agent.enable = true;

  # Keep Nix-managed command-line tools separate from the mutable PM cache of
  # the pre-Nix installation. The directory may hold optional runtime downloads,
  # but credentials, sessions, and all durable state remain in ~/.hermes.
  home.sessionVariables.HERMES_RUNTIME_DIR = "/home/max/.hermes/nix-runtime";

  services.hermes-agent = {
    enable = true;
    gateway.enable = true;
    hermesHome = "/home/max/.hermes";
    workingDirectory = "/home/max";
    package = hermesPackages.messaging;
    restart = "always";
    restartSec = 5;
    extraArgs = [ "run" ];

    extraPackages = [
      pkgs.chromium
      pkgs.ffmpeg
      pkgs.git
      pkgs.gh
      pkgs.gnugrep
      pkgs.gnused
      pkgs.nodejs_26
      pkgs.ripgrep
      pkgs.tigervnc
      pkgs.dbus
      pkgs.xauth
      pkgs.xdpyinfo
      pkgs.setxkbmap
      pkgs.xprop
      pkgs.xset
      pkgs.xsetroot
      pkgs.xfwm4
      pkgs.xfce4-panel
      pkgs.xfdesktop
      pkgs.xfce4-settings
      pkgs.xfce4-terminal
      pkgs.dejavu_fonts
      agentBrowser
      cuaDriver
    ];

    settings = {
      browser.headed = true;
      bot_desktop = {
        auto_start = true;
        geometry = "1440x900";
        idle_stop_minutes = 30;
        min_free_memory_mb = 1536;
      };
    };
  };

  # Match the supervision semantics of `hermes gateway install`, while keeping
  # browser/tool paths out of ~/.hermes/.env so activation cannot overwrite
  # the existing credentials file.
  systemd.user.services.hermes-agent = {
    Unit.StartLimitIntervalSec = 0;
    Service = {
      Environment = lib.mkAfter [
        "AGENT_BROWSER_EXECUTABLE_PATH=${pkgs.chromium}/bin/chromium"
        "CUA_DRIVER_RS_TELEMETRY_ENABLED=0"
        "HERMES_CUA_DRIVER_CMD=${cuaDriver}/bin/cua-driver"
        "HERMES_RUNTIME_DIR=/home/max/.hermes/nix-runtime"
        "HERMES_SUPERVISED_CHILD=1"
      ];
      RestartForceExitStatus = "75";
      SuccessExitStatus = "75";
      RestartPreventExitStatus = "78";
      KillMode = "mixed";
      KillSignal = "SIGTERM";
      TimeoutStopSec = 70;
      StandardOutput = "journal";
      StandardError = "journal";
    };
  };
}
