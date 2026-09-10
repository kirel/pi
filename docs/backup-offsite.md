# Independent offsite Borg backups

`backup-offsite.yml` configures the existing OMV NAS as two independent encrypted
Borg targets and schedules borgmatic on `homelab-nuc`. It preserves the existing
local `/tank/backups/homelab-configs` job. No disks are reformatted or purchased.

| Profile | Disk | Sources | Daily start (NUC local time) |
| --- | --- | --- | --- |
| important | Toshiba 1 TB, UUID `d47b4f30-8712-4368-8acf-574545ee6900` | Configs, database dumps, Immich library, Bilder/Videos/Sync/Musik | 03:00 + 0–30 min |
| full | Seagate 2 TB, UUID `2714e2f1-75fb-4395-b2f9-db68f4a6605a` | Everything above plus Filme/Shows | 05:00 + 0–30 min |

The Crucial 120 GB SSD remains mounted and available as reserve. There is no
mergerfs pool, RAID or cross-disk Borg repository. A failed HDD does not make the
other repository unreadable. Each repository deduplicates independently; shared
important data deliberately occupies space on both disks. The two disks in one
NAS are still one physical backup location.

## Deployment and ownership

```sh
uv run ansible-playbook backup-offsite.yml
```

Source selection, disk UUIDs and schedules live in
`group_vars/all/backup_offsite.yml`. The base NAS connectivity/hardware playbook
remains separate. Deploy the offsite playbook before distributing its new Borg
key to a freshly installed NAS, because it creates the target account.

`backup_repositories` validates each mounted UUID and ext4 filesystem, removes
only the unused legacy pool/shared-folder configuration through OMV RPC, and
creates the OMV-managed `borg` account. It refuses a populated legacy backup
directory or a shared folder referenced by another service. Original OMV
metadata is retained at `/root/omv-before-separate-borg-disks.xml` on the NAS.

The existing `ssh_keys` role creates the NUC's
`/root/.ssh/borg_backupnas_ed25519` key and installs its public half for `borg`.
The forced command `/usr/local/sbin/borg-offsite-serve` accepts Borg only,
restricts access to the two exact repository paths, and checks disk UUID/mounts
on every connection. An absent disk cannot redirect backups onto the SD card.
Management SSH as `daniel` from Ailab and the NUC remains available.

Traffic uses ordinary SSH over `backupnas.halfmoon-platy.ts.net`, with a pinned
host key. Each repo uses Borg repokey encryption and the existing Vault-managed
`vault_borg_passphrase`. New repo keys are independent even though the passphrase
is shared. Encrypted key exports are retained on the NUC under
`/root/.config/borg/offsite-key-exports/`. The repokey also resides in each repo.
An offline recovery plan must retain the passphrase/Vault recovery method;
the NUC's copies alone do not survive loss of the homelab.

## Consistent inputs and scope

The runner stages `/home/nuc/config` on `tank/offsite-staging`, preserving the
original relative restore paths. It replaces detected SQLite `.db`, `.sqlite`
and `.sqlite3` files with online SQLite backups, preserving file ownership and
mode. A read transaction pins the source snapshot, so continuous WAL writes
do not restart the incremental copy. The runner removes copied journal/WAL
sidecars. Music Assistant holds exclusive database locks, so its small config
directory is copied after briefly stopping `music-assistant-server`; it is
restarted immediately and also recovered by the cleanup handler after interruption.
This provides consistent individual SQLite databases, not a simultaneous snapshot of every application.

Logical PostgreSQL dumps cover `immich_postgres`, `litellm-postgres` and
`teslamate-db`. Immich's server is briefly stopped while its dump and the ZFS
library/media snapshots are captured, then restarted immediately. The long
transfer uses read-only bind mounts of staged configs, dumps and snapshots.
Cleanup unmounts these views, deletes only the runner's named snapshots and
restarts Immich if an interrupted preparation left a resume marker.

Files restore below `home/nuc/config`, `database-dumps`, `tank/immich/library`
and `tank/medien`. PostgreSQL dumps must be restored with PostgreSQL tooling;
raw live PostgreSQL files are not the database recovery mechanism. The Immich
library now also has the existing Sanoid production snapshot policy locally.

Excluded: AI model datasets, Time Machine/other existing backup repositories,
media downloading/downloads directories, generated caches, logs, temp,
node_modules, build/dist and the live LiteLLM PostgreSQL data directory.
This is a selected-data backup, not a bare-metal image or every ZFS dataset.

## Operation and verification

Run on the NUC:

```sh
systemctl start --no-block borgmatic-offsite@important.service
systemctl start --no-block borgmatic-offsite@full.service
systemctl list-timers 'borgmatic-offsite-*'
journalctl -u borgmatic-offsite@important.service -n 50
cat /var/lib/borg-offsite/status/important.json
```

A shared lock serializes offsite jobs. The local Borg job has a separate repo
and remains on its existing schedule. Do not run plain `borgmatic` against all
configs: offsite creation requires the runner's prepared read-only inputs.

Retention per repository: 14 daily, 8 weekly, 12 monthly, 2 yearly archives.
Each completed backup restores metadata, PostgreSQL dumps, a SQLite database
and an Immich image into a hash stream and compares SHA-256 with the prepared
source files. This checks real-file recovery without logging their contents.
It does not replace a full application restore rehearsal. Repository and
archive checks run weekly; data verification runs every four weeks. systemd and the status JSON record failures. No external notification
channel is configured by this playbook.

`borg-offsite smoke important` (or `full`) creates a small encrypted test archive,
extracts and compares its exact contents, checks the repository and removes only
that test archive. Run it while that repository is idle. For actual restores,
use the matching `/etc/borgmatic.d/offsite-<profile>.yaml` configuration, select
the desired archive and extract into a separate recovery directory. Never print
the rendered configuration: it contains the encryption passphrase.

On 2026-09-10 both repositories passed this encrypted round-trip and repository
check. Normal shell access with the backup key was rejected as intended.
Initial data backups were started; a complete initial archive and recovery of
real application data must be verified before relying on the offsite copy.
Physical offsite networking has not yet been tested.

Additional validation: the final complete Ansible rerun reported zero changes
and zero failures on both hosts. Seven forced-command/mount guard cases passed,
and the restore verifier rejected deliberately mismatched content. A concurrent
WAL-writer test confirmed a consistent SQLite snapshot and passed SQLite
`integrity_check`. The first Sanoid library snapshots were created automatically
on 2026-09-11. See the [SQLite backup API](https://www.sqlite.org/backup.html)
for the restart behavior addressed by the pinned read transaction.
