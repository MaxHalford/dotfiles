{ config, lib, ... }:

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
    openssh.authorizedKeys.keys = [
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHiaw75TP13e1YbzfHgzId3zEHuubpncaqhFk+5jRGax"
    ];
  };

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

  system.stateVersion = "26.05";
}
