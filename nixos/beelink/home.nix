{ lib, pkgs, hermesAgent, ... }:

let
  system = pkgs.stdenv.hostPlatform.system;
  hermesPackages = hermesAgent.packages.${system};

  # Hermes' PM artifacts are upstream Linux binaries rather than conventional
  # Nix packages. Copy and patch them so they use NixOS' dynamic linker and
  # expose stable commands on PATH.
  cuaDriver = pkgs.stdenvNoCC.mkDerivation {
    pname = "hermes-cua-driver";
    version = hermesPackages.pm-cua-driver.version;
    src = builtins.elemAt hermesPackages.pm-cua-driver.srcs 0;
    nativeBuildInputs = [ pkgs.autoPatchelfHook ];
    buildInputs = [
      pkgs.libxkbcommon
      pkgs.libx11
      pkgs.libxi
      pkgs.stdenv.cc.cc.lib
    ];
    unpackPhase = ''
      mkdir source
      cd source
      tar -xzf "$src"
    '';
    installPhase = ''
      runHook preInstall
      mkdir -p "$out/libexec/cua-driver" "$out/bin"
      cp -a ./* "$out/libexec/cua-driver/"
      chmod +x "$out/libexec/cua-driver/cua-driver" "$out/libexec/cua-driver/cua-cursor-theme"
      ln -s "$out/libexec/cua-driver/cua-driver" "$out/bin/cua-driver"
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

  home.packages = [ pkgs.herdr ];

  xdg.configFile."herdr/config.toml" = {
    source = ./herdr.toml;
    force = true;
  };

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
      cuaDriver
    ];

    settings = {
      browser = {
        executable_path = "${pkgs.chromium}/bin/chromium";
        headed = true;
      };
      bot_desktop = {
        auto_start = true;
        geometry = "1440x900";
        idle_stop_minutes = 30;
        min_free_memory_mb = 1536;
      };
    };
  };

  systemd.user.services.herdr = {
    Unit = {
      Description = "Herdr persistent agent workspace server";
      After = [ "network-online.target" ];
      Wants = [ "network-online.target" ];
      StartLimitIntervalSec = 0;
    };
    Service = {
      ExecStart = "${pkgs.herdr}/bin/herdr server";
      Restart = "on-failure";
      RestartSec = 5;
      KillMode = "mixed";
    };
    Install.WantedBy = [ "default.target" ];
  };

  # Match the supervision semantics of `hermes gateway install`, while keeping
  # browser/tool paths out of ~/.hermes/.env so activation cannot overwrite
  # the existing credentials file.
  systemd.user.services.hermes-agent = {
    Unit.StartLimitIntervalSec = 0;
    Service = {
      Environment = lib.mkAfter [
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
