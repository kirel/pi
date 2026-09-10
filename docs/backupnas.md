# OpenMediaVault backup NAS

`backupnas` is an existing OMV appliance, managed by the `backup_nas` inventory
group. Ansible manages Tailscale, Wi-Fi, the Penta HAT boot settings and SSH management
access. OMV retains ownership of storage, filesystems, shares, users, sshd and
LAN DHCP networking. The general `basic` and `pi` roles deliberately do not run here.

## Deployment

```sh
uv run ansible-playbook setup.yml --limit backupnas --tags backupnas,ssh-keys
```

The central `ssh_keys` role handles all key creation and authorization. The NAS
role only configures SSH aliases and host-key pinning. These tasks delegate to
`ailab-ubuntu` (user `daniel`) and `homelab-nuc` (user `root`); both must be
reachable from the Ansible controller. Private keys stay on their source hosts.
Existing authorized keys and OMV's separate public-key store are preserved.
The NAS is also included in the central `ssh_keys` play, using the existing
Ailab key. `--limit backupnas --tags ssh-keys` refreshes that distribution and
the NAS-specific NUC key, host-key pinning and client aliases.
Changes to the HAT boot configuration trigger a reboot at the end of the play.

For recovery on the local LAN, override the inventory address:

```sh
uv run ansible-playbook setup.yml --limit backupnas --tags backupnas,ssh-keys -e ansible_host=backupnas.local
```

## Management and offsite operation

From `daniel@ailab-ubuntu` or `root@homelab-nuc`:

```sh
ssh backupnas
ssh backupnas 'sudo -n hostname'
```

The SSH alias uses `backupnas.halfmoon-platy.ts.net`, authenticates as `daniel`,
and pins the NAS's existing Ed25519 host key. This is ordinary OpenSSH over
Tailscale, using the existing sudo privileges. Tailscale SSH is disabled.
Ailab reaches the tailnet through the existing route via `192.168.50.5` and the
NUC's LAN-to-tailnet NAT; it does not need a separate Tailscale installation.

Tailscale uses the existing encrypted OAuth configuration, the `homelab` tag,
and a persistent, preauthorized node. The NAS neither advertises nor accepts
subnet routes, and keeps DHCP-provided DNS. Its Ethernet interface already uses
DHCP, so it can obtain an address and gateway at the offsite location.

Verified tailnet address: `100.118.19.28`. The node reports `tag:homelab` and no
key expiry; `tailscaled` starts automatically. The inventory uses the tailnet
FQDN rather than the local DHCP address (`192.168.50.202` during setup).

The legacy OMV WireGuard custom profile `Home` is disabled in OMV's database,
and `wg-quick@wgnet_Home` is stopped and disabled. Its stored configuration is
preserved locally for recovery. This removes its default-route and DNS takeover.

The separate `backup-offsite.yml` playbook manages the Borg repositories and
scheduled source jobs described in [Offsite backups](backup-offsite.md). The NAS
base role remains responsible for connectivity and hardware settings.

## Wi-Fi with LAN preferred

`backupnas_wifi_profiles` in `group_vars/backup_nas.yml` stores only profile names,
SSIDs or SSID references and password references in the 1Password `homelab` vault.
Both home and offsite profiles are configured. Each profile requires exactly one
of `ssid` and `ssid_ref`; passwords always use a reference:

```yaml
backupnas_wifi_profiles:
  - name: home
    ssid_ref: "op://homelab/WLAN Zuhause/Netzwerkname"
    password_ref: "op://homelab/WLAN Zuhause/Passwort des drahtlosen Netzwerks"
    priority: 10
  - name: offsite
    ssid: "Telekom MN 5 GHz"
    password_ref: "op://homelab/WLAN Marian/Passwort des drahtlosen Netzwerks"
    priority: 5
```

Deploy only Wi-Fi with:

```sh
uv run ansible-playbook setup.yml --limit backupnas --tags backupnas-wifi
```

The existing `op-sa` service account on Ailab reads just those fields. A helper
derives WPA2 PSKs and sends the configuration directly over authenticated SSH to
`/etc/wpa_supplicant/wpa_supplicant-wlan0.conf` on the NAS, owned by root with
mode `0600`. Resolved values never return to the Ansible controller, enter command
arguments or get saved in the repository. Provisioning tasks suppress logs and
diffs. The saved keys allow booting offsite without access to 1Password or Ailab.

Only a revision of the non-secret references/settings is compared for
idempotence. After changing a field's value in 1Password while keeping its
reference unchanged, explicitly refresh the credentials:

```sh
uv run ansible-playbook setup.yml --limit backupnas --tags backupnas-wifi -e backupnas_wifi_refresh_credentials=true
```

`wpa_supplicant@wlan0` selects an available configured network; higher profile
priority wins when several are available. Profiles support WPA2-Personal and
mixed WPA2/WPA3 networks, not WPA3-only or enterprise authentication. The country
code is `DE`. Ansible owns Wi-Fi only; do not also configure it in OMV or Netplan.
The role checks for such conflicting ownership before applying changes.

`systemd-networkd` obtains Wi-Fi addresses, gateway and DNS via DHCP/IPv6 RA.
The Wi-Fi route metric is 4096, below the existing LAN preference (IPv4 metric
1024). Wi-Fi can remain connected while LAN carries traffic. Removing LAN's
carrier withdraws its routes, allowing Wi-Fi to take over; this does not detect
an upstream internet outage while LAN carrier remains present. Wi-Fi is not
required for reaching systemd's online target.

Validated on 2026-09-11: home association completed, DHCP assigned
`192.168.50.155`, the default route selected LAN, and an HTTPS request explicitly
bound to `wlan0` succeeded. The supplicant is enabled at boot. A physical LAN
disconnect/reconnect test was deferred because a Borg process was active.
Both profiles are provisioned; association with the offsite network remains to
be tested at that location.

## Hardware

Initial SSH inspection on 2026-09-10:

- Raspberry Pi 5 Model B Rev 1.0, four Cortex-A76 cores at up to 2.4 GHz.
- 8 GB RAM (7.9 GiB reported).
- 16 GB microSD system disk (14.8 GiB reported), ext4 root with OMV writecache.
- Gigabit Ethernet, negotiated at 1000 Mb/s full duplex; Wi-Fi disabled.
- Radxa Penta SATA HAT, reported physically connected by Daniel.
- JetKVM USB emulation device connected.
- Debian 13 (trixie), OMV 8.0-13, kernel 6.12.47+rpt-rpi-2712 at initial inspection.
- OMV borgbackup, mergerfs, bcache, writecache and WireGuard plugins installed.

After PCIe activation, all three existing ext4 filesystems were mounted by OMV:

| Disk | Capacity | Power-on hours | SMART observations |
| --- | --- | --- | --- |
| Crucial CT120BX500SSD1 | 120 GB | 33,189 | Overall passed; no reallocated/pending/uncorrectable blocks reported |
| Toshiba MQ01ABD100 | 1 TB | 5,643 | Overall passed; no reallocated/pending/uncorrectable sectors reported |
| Seagate ST2000LM007-1R8174 | 2 TB | 49,669 | Overall passed; 5 reallocated sectors, no pending/uncorrectable sectors |

The unused mergerfs `backup_pool` and its unused shared-folder entry were
removed through OMV on 2026-09-10. All three ext4 filesystems are preserved and
mounted individually. The HDDs host independent Borg repositories; the SSD is
reserve. These SMART readings are a snapshot, not an extended disk self-test.
Important data is included on both HDDs, given the Seagate's age and sectors.

## Kernel maintenance

Kernel upgrades are explicit maintenance, not part of the regular NAS role.
The one-off update on 2026-09-10 used the configured Raspberry Pi APT repository,
upgrading the already installed `linux-image-rpi-2712`, `linux-headers-rpi-2712`,
`linux-image-rpi-v8`, `linux-headers-rpi-v8` and `raspi-firmware` packages and their
dependencies. Old kernel packages are retained. Refresh APT indexes after reboot:
OMV writecache keeps `/var/lib/apt/lists` in a temporary overlay.

The `/var/tmp` overlay is only 196 MiB and is too small for building these
initramfs images. Use a root-owned temporary directory on the system filesystem
as `TMPDIR` for kernel package configuration, then remove it after completion.
Do not reboot until `dpkg --configure -a` and `dpkg --audit` succeed and the
matching initramfs files have been generated in `/boot/firmware`.

The external PCIe interface was initially disabled: no SATA controller or disks
were enumerated. The role enables `dtparam=pciex1` and leaves the default PCIe
Gen 2 speed in place. The optional `backupnas_penta_dma32` setting controls the
`pcie-32bit-dma-pi5` overlay. With the original 6.12.47 kernel and that overlay,
IDENTIFY timeouts and no AHCI interrupts were observed; without it all three
disks were recognized. **Final validated configuration: kernel
`6.18.39+rpt-rpi-2712`, firmware `1:1.20260907-1`, DMA overlay enabled.**

## Validation and remaining observations

- All three disks and their existing ext4 filesystems are present after reboot;
  OMV manages their individual mounts.
- SSH as `daniel`, with passwordless sudo, succeeds over Tailscale from Ailab
  and the NUC. The observed destination address is `100.118.19.28:22`.
- Ailab sent 1 MiB through SSH over Tailscale to a uniquely named temporary file
  on the mounted pool. The remote file was flushed, read back and compared by
  SHA-256; the file was removed afterwards.
- The package audit is clean. Syntax checks and lint for the new tasks pass.
- A final full NAS/key-management run completed with `ok=61`, `changed=0`,
  `failed=0`, confirming idempotence after the kernel reboot.
- OMV's SSD `quotaon` unit reports `File exists` at boot because the SSD's ext4
  filesystem already has internal user/group quotas enabled. `quotaon -p`
  confirms both are on. This does not prevent mounting or I/O. The HDDs still
  use OMV's older external quota files and log a deprecation warning. No quota
  migration or filesystem feature changes were made during this setup.
- Physical operation at the offsite location remains to be tested. Backup-job
  setup and validation are documented separately in [Offsite backups](backup-offsite.md).

References:

- [Radxa Penta HAT on Raspberry Pi 5](https://docs.radxa.com/en/accessories/storage/penta-sata-hat/penta-for-rpi5)
- [Tailscale Linux installation](https://tailscale.com/docs/install/linux)
- [OpenMediaVault SSH configuration](https://docs.openmediavault.org/en/8.x/administration/services/ssh.html)
