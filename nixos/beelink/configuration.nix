{ config, lib, pkgs, ... }:

{
  imports = [ ./hardware-configuration.nix ];

  boot.loader.systemd-boot = {
    enable = true;
    configurationLimit = 10;
    editor = false;
  };
  boot.loader.efi = {
    canTouchEfiVariables = true;
    efiSysMountPoint = "/boot";
  };
  fileSystems."/boot".options = lib.mkForce [ "fmask=0077" "dmask=0077" ];

  zramSwap.enable = true;

  nix.settings.experimental-features = [ "nix-command" "flakes" ];
  nix.gc = {
    automatic = true;
    dates = "weekly";
    options = "--delete-older-than 30d";
  };

  # Reboot during the Sunday maintenance window only when an already-built and
  # reviewed system generation has changed the kernel, modules, or initrd.
  # Update discovery and lock-file refreshes stay separate from root activation.
  systemd.services.reboot-into-pending-generation = {
    description = "Reboot into a reviewed pending NixOS generation";
    serviceConfig.Type = "oneshot";
    path = [ pkgs.coreutils pkgs.systemd ];
    script = ''
      pending_profile="$(${pkgs.coreutils}/bin/readlink -f /nix/var/nix/profiles/system)"
      booted="$(${pkgs.coreutils}/bin/readlink /run/booted-system/{initrd,kernel,kernel-modules})"
      pending="$(${pkgs.coreutils}/bin/readlink "$pending_profile"/{initrd,kernel,kernel-modules})"

      if [ "$booted" = "$pending" ]; then
        echo "No pending kernel, module, or initrd change; reboot not required."
        exit 0
      fi

      current_profile="$(${pkgs.coreutils}/bin/readlink -f /nix/var/nix/profiles/system)"
      if [ "$current_profile" != "$pending_profile" ]; then
        echo "System profile changed during the check; refusing to reboot."
        exit 1
      fi

      echo "Pending boot artifacts differ; rebooting into the reviewed generation now."
      ${pkgs.systemd}/bin/systemctl reboot
    '';
  };

  systemd.timers.reboot-into-pending-generation = {
    description = "Weekly conditional reboot for reviewed NixOS updates";
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnCalendar = "Sun 10:00";
      Persistent = false;
      Unit = "reboot-into-pending-generation.service";
    };
  };

  networking.hostName = "beelink-nixos";
  networking.useDHCP = false;
  networking.interfaces.enp1s0.useDHCP = true;
  networking.firewall = {
    enable = true;
    allowedUDPPorts = [ config.services.tailscale.port ];
    interfaces.enp1s0.allowedTCPPorts = [ 22 ];
    interfaces.tailscale0.allowedTCPPorts = [ 22 ];
  };

  time.timeZone = "Europe/Paris";

  users.users.max = {
    isNormalUser = true;
    extraGroups = [ "wheel" ];
    linger = true;
    openssh.authorizedKeys.keys = [
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHiaw75TP13e1YbzfHgzId3zEHuubpncaqhFk+5jRGax"
    ];
  };

  environment.systemPackages = with pkgs; [
    git
    gh
    ripgrep
  ];

  services.openssh = {
    enable = true;
    openFirewall = false;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "no";
    };
  };
  services.tailscale.enable = true;
  services.fstrim.enable = true;
  services.smartd.enable = true;

  system.stateVersion = "26.05";
}
