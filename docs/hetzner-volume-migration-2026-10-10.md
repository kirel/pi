# Hetzner data volume

Host: `ubuntu-8gb-fsn1-1` (`100.82.91.51`). Existing 100 GiB Hetzner Volume
`107098820`, ext4 UUID `c42a3e4a-d140-487c-bc9c-383501869bc9`.

## Layout

| Volume directory | Bind mount / application path |
| --- | --- |
| `/mnt/HC_Volume_107098820/daniel-home` | `/home/daniel` |
| `/mnt/HC_Volume_107098820/hermes-agents` | `/opt/hermes-agents` |

Applications retain their existing paths, ownership, ACLs, extended attributes,
symlinks and hardlinks. This includes bare-metal Hermes state, Daniel's projects
and user tooling, Docker Hermes data and environments, sidecar data and
indexproxy's project/data bind mounts.

`/home/marian`, `/home/linuxbrew`, Docker/containerd storage and the OS remain on
the root filesystem. `/home/marian` is a separate Linux account, not Marian's
Docker Hermes data directory.

## Ansible ownership

`group_vars/hetzner.yml`, `roles/hetzner_storage` and `hetzner-storage.yml` own
fstab and systemd dependencies. The role also runs before other Hetzner roles in
`setup.yml`.

```sh
uv run ansible-playbook hetzner-storage.yml --syntax-check
uv run ansible-playbook hetzner-storage.yml
```

The role does not copy data. It requires `.migration-complete` on the volume
before binding application paths. Docker (service and socket) and
`user@1000.service` require the volume and both bind mounts, with mount-point
assertions. The volume and bind mounts use `nofail` so a missing volume does not
prevent the host from booting, but dependent applications must not start against
empty directories.

## Migration and recovery

The cutover runs as a root systemd service independently of Daniel's SSH/Mosh
sessions. After a live pre-copy, it stops the watchdog, cron, user services and
containers, terminates remaining user writers, and runs a final `rsync -aHAXx
--numeric-ids --delete-delay`. The final rsync completed successfully for both trees. The full checksum
comparison of Daniel's home found no differences. The additional Docker-data
checksum scan was stopped at the user's request to end the maintenance window;
no complete checksum claim is made for that tree.

Original directories are renamed to `/home/daniel.pre-volume` and
`/opt/hermes-agents.pre-volume`. Before restarting applications, a failed cutover
restores the old directories and fstab. Once applications have resumed writing,
rollback requires another controlled shutdown and reconciliation of new data;
restoring the old snapshot alone would lose subsequent writes.

Root-only migration records, the prior fstab and the original running-container
list are under `/root/hetzner-volume-migration` on Hetzner.

Before removing original directories, back them up to:

`homelab-nuc:/root/backups/hetzner-volume-107098820/original-data.tar.zst.enc`

The archive uses GNU tar ACL/xattr/numeric-owner preservation, zstd, and OpenSSL
AES-256-CBC with PBKDF2 (200000 iterations). Its root-only `recovery.key` is in the
same backup directory; preserve that file with the archive. Verify the decrypted
compressed stream's SHA-256 against the source and check the complete archive.
This is a migration snapshot, not a recurring backup of future changes.

To extract on a recovery host, first create an empty directory on a filesystem
with sufficient space. As root, using the actual backup directory:

```sh
set -o pipefail
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -pass file:recovery.key -in original-data.tar.zst.enc |
  zstd -dc |
  tar --acls --xattrs --numeric-owner -xpf - -C /path/to/empty-recovery-directory
```

Do not extract directly over running applications. Restored paths have the
`.pre-volume` suffix. If the volume is unavailable and Daniel's home cannot be
mounted, use Hetzner's console/rescue access; direct root SSH remains disabled.

## Functional verification

- Storage and full setup playbooks pass syntax checks. Applying the storage
  playbook twice completed without errors; the second run reported `changed=0`.
- Both application paths resolve to the volume UUID. Docker service/socket and
  Daniel's user manager have the expected mount dependencies.
- All 19 previously running containers restarted. The three user services
  (`hermes-gateway`, `hermes-dashboard`, `ai-video-projects`) are active.
- All five Docker Hermes instances passed actual API chat requests with
  `mcp__litellm__fetch_fetch` against `https://example.com`; stored tool results
  confirm the fetch rather than relying only on the model's answer.
- Bare-metal Hermes passed the same MCP fetch through its normal CLI startup,
  including its existing 1Password integration and dynamic tool discovery.
  Session `20261011_001050_cee4dc` records the successful MCP result.
- Marian's calendar script passed through the native cron script runner using
  `/opt/data/.venvs/google-api/bin/python`; no report was sent. Both miniapp
  backends and their public HTTPS URLs returned HTTP 200. Dashboard, video-project UI and indexproxy health
  also returned HTTP 200.
- The first bare-metal gateway start took several minutes while reading its
  approximately 1.6 GiB state database on the volume. No Hermes runtime or
  personal configuration changes were made as part of the migration.

The subsequent full host reboot passed: both bind mounts were automatically
restored, all 19 containers were running, all three user services were active,
and all six gateways reported fresh connected Telegram/API states. API health
checks passed for each Docker gateway and the bare-metal gateway; dashboard,
video UI and indexproxy health also passed. Full readiness was confirmed at
334 seconds of host uptime. This several-minute cold start of bare-metal Hermes
should be included in future maintenance windows.

## Completed storage cleanup

After the successful reboot and the external archive's decryption, tar validation
and source-stream SHA-256 comparison, both original `.pre-volume` directories
were removed. The temporary full container inspection dump was also removed.
Both public Marian miniapp URLs returned HTTP 200 after reboot.

Final measured filesystem state:

| Filesystem | Used | Available | Usage reported by df |
| --- | --- | --- | --- |
| Root (`/`) | 18.4 GiB | 53.3 GiB | 26% |
| Data volume | 41.9 GiB | 50.9 GiB | 46% |

The root filesystem had approximately 2 GiB available before migration.
The external encrypted migration archive occupies approximately 24.15 GiB.
