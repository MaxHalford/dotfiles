# Beelink NixOS server

This configuration is for the headless NixOS 26.05 server installed on the Beelink's entire 1 TB SSD on 2026-09-25. It enables SSH with Max's MacBook public key and Tailscale for remote access. The `hardware-configuration.nix` file was generated on this machine after partitioning.

## Disk layout

The target is the Crucial P310 1 TB NVMe SSD at `/dev/nvme0n1`. The NixOS USB installer is a separate 14.8 GiB drive at `/dev/sda`. The installed layout has a 2 GiB FAT32 EFI System Partition at `/dev/nvme0n1p1`, mounted at `/boot`, and a 929.5 GiB ext4 root partition at `/dev/nvme0n1p2`. All former Windows partitions were replaced.

## Reinstall

Boot the NixOS USB, partition and format the NVMe SSD, and mount the root partition at `/mnt` and the EFI System Partition at `/mnt/boot`. Run `nixos-generate-config --root /mnt`, then place this `configuration.nix` beside the generated `hardware-configuration.nix` at `/mnt/etc/nixos/`. Run `nixos-install --no-root-passwd`. Before rebooting, set the `max` account password with `nixos-enter --root /mnt -c 'passwd max'` so sudo works after the first boot.

## Access

With Tailscale connected on the MacBook, use `ssh max@100.103.169.94`. On the local network, use `ssh max@192.168.1.80`. The short hostname does not resolve because MagicDNS is disabled on this tailnet. SSH password login is disabled; the MacBook's `~/.ssh/id_ed25519` key is authorized. Change the temporary local account password with `passwd` after signing in. No router port forwarding is needed.

The server was rebooted after Tailscale enrollment, and SSH over its Tailscale address, `sshd`, and `tailscaled` all came back successfully.
