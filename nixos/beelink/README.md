# Beelink NixOS host

This directory defines the Beelink SER8 server, including its always-on Hermes Telegram gateway, Chromium, Computer Use, and Bot Screen dependencies.

Hermes keeps all durable state under `/home/max/.hermes`. The Nix configuration does not manage or replace `.env` or `auth.json`; credentials, sessions, skills, memory, cron jobs, and browser state remain outside Git.

## First migration

Run these steps from the repository root. Build the new generation before stopping the current gateway:

```sh
nix --extra-experimental-features 'nix-command flakes' \
  build .#nixosConfigurations.beelink-nixos.config.system.build.toplevel
```

The live pre-migration generation does not yet enable flakes globally, so the explicit feature flag is required. Build the matching `nixos-rebuild` executable as well:

```sh
rebuild="$(nix --extra-experimental-features 'nix-command flakes' \
  build --no-link --print-out-paths \
  .#nixosConfigurations.beelink-nixos.config.system.build.nixos-rebuild)"
```

Back up the mutable Hermes state and the legacy service definition:

```sh
backup="$HOME/hermes-migration-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup"
cp -a "$HOME/.hermes" "$backup/hermes-state"
cp -a "$HOME/.config/systemd/user/hermes-gateway.service" "$backup/" 2>/dev/null || true
cp -a "$HOME/.config/systemd/user/hermes-gateway.service.d" "$backup/" 2>/dev/null || true
```

Immediately before switching, stop and disable the legacy unit. Do not uninstall it yet; keeping the file makes rollback immediate.

```sh
systemctl --user disable --now hermes-gateway.service
sudo "$rebuild/bin/nixos-rebuild" switch \
  --option experimental-features 'nix-command flakes' \
  --flake .#beelink-nixos
```

This order prevents the old `hermes-gateway.service` and the declarative `hermes-agent.service` from using the same bot credentials concurrently.

## Verify after switching

```sh
systemctl --user is-enabled hermes-agent.service
systemctl --user status hermes-agent.service
hermes gateway status
hermes computer-use status
hermes computer-use screen status
journalctl --user -u hermes-agent.service -n 100 --no-pager
```

Confirm that Telegram receives and answers a message, then verify that only the declarative unit owns a gateway process:

```sh
systemctl --user is-active hermes-gateway.service || true
systemctl --user show hermes-agent.service -p MainPID -p SubState
pgrep -af 'hermes.*gateway'
```

There must be one gateway, owned by `hermes-agent.service`, and the legacy unit must be inactive. Once verified, remove the obsolete files:

```sh
rm -f "$HOME/.config/systemd/user/hermes-gateway.service"
rm -rf "$HOME/.config/systemd/user/hermes-gateway.service.d"
systemctl --user daemon-reload
```

Then perform one controlled reboot and repeat the verification checks.

## Weekly update check and conditional reboot

A separate Hermes notification runs every Sunday at 09:00 Europe/Paris. It checks Hermes, NixOS inputs, gateway health, failed units, disk space, and whether a fresh generation builds. It does not grant a mutable remote branch unattended root access: dependency refreshes remain reviewed `flake.lock` changes that are built before activation.

At 10:00, a system timer compares the booted kernel, modules, and initrd with the already-reviewed system profile. It rechecks that the profile did not change during the comparison, then reboots immediately only when those boot artifacts differ; otherwise it exits without rebooting. Inspect it with:

```sh
systemctl status reboot-into-pending-generation.timer
systemctl list-timers reboot-into-pending-generation.timer
journalctl -u reboot-into-pending-generation.service -n 100 --no-pager
```

Failed builds never change the system profile. Existing NixOS boot generations remain available for rollback.

## Roll back

If activation or verification fails, stop and detach the declarative user unit before restoring the legacy service. This prevents both gateways from surviving the system rollback:

```sh
systemctl --user disable --now hermes-agent.service || true
rm -f "$HOME/.config/systemd/user/default.target.wants/hermes-agent.service"
rm -f "$HOME/.config/systemd/user/hermes-agent.service"
systemctl --user daemon-reload
rebuild="${rebuild:-$(nix --extra-experimental-features 'nix-command flakes' \
  build --no-link --print-out-paths \
  .#nixosConfigurations.beelink-nixos.config.system.build.nixos-rebuild)}"
sudo "$rebuild/bin/nixos-rebuild" switch --rollback \
  --option experimental-features 'nix-command flakes'
systemctl --user daemon-reload
systemctl --user enable --now hermes-gateway.service
```

Verify rollback uniqueness with `pgrep -af 'hermes.*gateway'`: only the legacy gateway should remain. If the legacy unit files were already removed, copy them back from the migration backup before the first `daemon-reload`.

## Recovery boundaries

The Nix configuration makes the gateway, browser dependencies, Computer Use driver, and Bot Screen dependencies reproducible. It cannot configure the firmware's power-loss behavior or provide an off-machine backup. Set **Restore on AC Power Loss** to **Power On** in the BIOS and back up `/home/max/.hermes` to another machine or storage provider.

SSH is currently allowed on both the LAN interface `enp1s0` and Tailscale. Remove `interfaces.enp1s0.allowedTCPPorts = [ 22 ];` from `configuration.nix` if administration should be tailnet-only.
