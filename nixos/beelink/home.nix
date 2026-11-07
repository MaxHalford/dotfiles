{ config, lib, pkgs, hermesAgent, ... }:

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

  programs = {
    home-manager.enable = true;
    hermes-agent.enable = true;

    bat.enable = true;

    direnv = {
      enable = true;
      nix-direnv.enable = true;
    };

    eza = {
      enable = true;
      enableZshIntegration = true;
      git = true;
      icons = "auto";
      extraOptions = [ "--group-directories-first" ];
    };

    fzf = {
      enable = true;
      enableZshIntegration = true;
    };

    jq.enable = true;
    ripgrep.enable = true;

    zoxide = {
      enable = true;
      enableZshIntegration = true;
    };

    zsh = {
      enable = true;
      enableCompletion = true;
      autosuggestion = {
        enable = true;
        highlight = "fg=5";
      };
      syntaxHighlighting.enable = true;
      defaultKeymap = "emacs";

      history = {
        expireDuplicatesFirst = true;
        extended = true;
        ignoreAllDups = true;
        path = "${config.xdg.dataHome}/zsh/history";
        save = 100000;
        share = true;
        size = 100000;
      };

      oh-my-zsh = {
        enable = true;
        plugins = [ "git" ];
      };

      plugins = [
        {
          name = "powerlevel10k";
          src = pkgs.zsh-powerlevel10k;
          file = "share/zsh-powerlevel10k/powerlevel10k.zsh-theme";
        }
        {
          name = "zsh-fzf-history-search";
          src = pkgs.zsh-fzf-history-search;
          file = "share/zsh-fzf-history-search/zsh-fzf-history-search.zsh";
        }
      ];

      initContent = lib.mkAfter ''
        # Match the Mac's completion and history-search behavior.
        bindkey -M emacs '^I' expand-or-complete
        bindkey -M viins '^I' expand-or-complete
        zstyle ':completion:*' menu select
        [[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh

        # Keep optional, host-local secrets and overrides outside Git.
        [[ ! -f ~/.secrets ]] || source ~/.secrets
        [[ ! -f ~/.zshrc.local ]] || source ~/.zshrc.local
      '';
    };
  };

  home.packages = with pkgs; [
    codex
    fd
    gh
    git
    herdr
    nodejs_26
    rtk
    tree
    uv
  ];

  home.file = {
    # Reuse the platform-neutral prompt from the Mac without importing the
    # Mac-specific shell bootstrap, Homebrew paths, or Keychain commands.
    ".p10k.zsh".source = ../../zsh/.p10k.zsh;

    # Codex configuration, credentials, and sessions stay mutable and private
    # in ~/.codex. Only safe global instructions and shared skills are managed.
    ".codex/AGENTS.md".source = ./codex-agents.md;
    ".codex/RTK.md".source = ./RTK.md;
    ".agents/skills" = {
      source = ../../agents/skills;
      recursive = true;
    };
  };

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
