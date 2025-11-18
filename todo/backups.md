# Homelab Backup Strategy - Final Implementation Plan

## Overview

**Three-tier backup strategy** combining ZFS snapshots, local Borg, and remote Borg to Hetzner Storage Box.

### Strategy Summary

```
┌─────────────────────────────────────────┐
│            Homelab-NUC                  │
│                                         │
│  Tier 1: ZFS Snapshots (local)         │
│  ├── tank/medien@snapshots              │
│  ├── tank/immich@snapshots              │
│  ├── tank/ai-models@snapshots           │
│  └── tank/config@snapshots              │
│                                         │
│  Tier 2: Borg (local)                   │
│  └── /tank/backups/homelab-configs      │
│      └── Only service configs           │
│                                         │
│  Tier 3: Borg (remote)                  │
│      └── Hetzner Storage Box            │
│          └── Everything (6TB)           │
└─────────────────────────────────────────┘
```

## Why This Architecture

### Separation of Concerns
- **ZFS Snapshots**: Instant rollback for common issues (30 sec)
- **Borg Local**: Fast config restores without touching data (5 min)
- **Borg Remote**: Complete disaster recovery (6-24 hours)
- **ML Models**: Not backed up (re-downloadable)

### Recovery Scenarios

| Scenario | Method | Time | Scope |
|----------|--------|------|-------|
| **Config corruption** | Borg local | 5 min | Configs only |
| **Accidental delete** | ZFS rollback | 30 sec | Any dataset |
| **Disk failure** | ZFS mirror | 0 sec | Hardware redundancy |
| **Server death** | Borg Hetzner | 6-24 hours | Everything |
| **Ransomware** | Borg Hetzner | 6-24 hours | Everything (off-site) |

## Option A: Dual Borg Approach (Recommended)

### Repository Structure

**Local Borg Repository (Fast Access)**
```
/tank/backups/homelab-configs/
```
- **Scope**: Only `/home/nuc/config/` (30+ service configs)
- **Size**: ~10GB
- **Purpose**: Quick config restores (5 minutes)
- **Encryption**: repokey

**Remote Borg Repository (Hetzner Storage Box)**
```
Hetzner Storage Box: homelab-backup/
```
- **Scope**: Everything (configs + all ZFS data)
  - `/home/nuc/config/`
  - `/tank/medien/`
  - `/tank/immich/`
  - `/tank/ai-models/`
  - `/tank/config/`
  - `/tank/timemachine/`
- **Size**: ~6TB (initial full backup)
- **Purpose**: Complete disaster recovery
- **Encryption**: repokey

### Retention Policies

**Local Borg (Configs)**
```bash
--keep-hourly=24 \
--keep-daily=7 \
--keep-weekly=4 \
--keep-monthly=12
```
- Keep 24 hourly backups (for quick config fixes)
- Keep 7 daily backups
- Keep 4 weekly backups
- Keep 12 monthly backups

**Remote Borg (Everything)**
```bash
--keep-weekly=8 \
--keep-monthly=12 \
--keep-yearly=3
```
- Keep 8 weekly backups (2 months)
- Keep 12 monthly backups (1 year)
- Keep 3 yearly backups

**ZFS Snapshots (Sanoid)**
- 24 hourly snapshots
- 7 daily snapshots
- 4 weekly snapshots
- 12 monthly snapshots

## Implementation Steps

### Phase 1: Enable ZFS Snapshots (Sanoid)

**Pre-requisite**: Sanoid is already installed (see `roles/zfs/defaults/main.yml:89`)

**Action**: Enable in ZFS defaults
```yaml
# roles/zfs/defaults/main.yml
zfs_snapshots_enabled: true
```

**Deploy**:
```bash
uv run ansible-playbook setup.yml --tags zfs --limit homelab
```

### Phase 2: Install Borg on All Hosts

**Add to roles/basic/tasks/main.yml**:
```yaml
- name: Install BorgBackup
  apt:
    name: borgbackup
    state: present
```

**Or create dedicated `roles/borg/` role**:
```yaml
# roles/borg/tasks/main.yml
- name: Install BorgBackup
  apt:
    name: borgbackup
    state: present

- name: Create backup directory structure
  file:
    path: "{{ item }}"
    state: directory
    mode: '0750'
    owner: nuc
    group: nuc
  loop:
    - /tank/backups/homelab-configs
    - /mnt/hetzner

- name: Set up SSH directory
  file:
    path: /root/.ssh
    state: directory
    mode: '0700'
```

### Phase 3: Create Local Borg Repository

**On homelab-nuc**:
```bash
ssh root@homelab-nuc.lan
cd /tank/backups

# Initialize repository with encryption
borg init --encryption=repokey /tank/backups/homelab-configs

# Set ownership
chown -R nuc:nuc /tank/backups/homelab-configs
chmod 750 /tank/backups/homelab-configs
```

### Phase 4: Create Remote Borg Repository

**Mount Hetzner Storage Box**:
```bash
# On homelab-nuc
ssh root@homelab-nuc.lan

# Create SSHFS mount point
mkdir -p /mnt/hetzner

# Mount Hetzner Storage Box
sshfs root@storage-xxx.your-box.de:/backups /mnt/hetzner

# Test connectivity
ls -la /mnt/hetzner
```

**Initialize remote repository**:
```bash
# Initialize on Hetzner
borg init --encryption=repokey /mnt/hetzner/homelab-backup

# Set ownership
chown -R nuc:nuc /mnt/hetzner
```

**Note**: Hetzner Storage Box credentials from secrets.yml

### Phase 5: Create Backup Scripts

**Script 1: Local Config Backup**
```bash
# /usr/local/bin/borg-backup-local-configs.sh
#!/bin/bash

set -euo pipefail

export BORG_REPO=/tank/backups/homelab-configs
export BORG_PASSPHRASE='${borg_passphrase}'

# Prune old backups
echo "Pruning old local backups..."
borg prune -v --list \
    --keep-hourly=24 \
    --keep-daily=7 \
    --keep-weekly=4 \
    --keep-monthly=12

# Create backup
echo "Creating local config backup..."
borg create \
    --info \
    --stats \
    --compression lz4 \
    --exclude-caches \
    --exclude '/home/nuc/config/*/cache' \
    --exclude '/home/nuc/config/*/logs' \
    --exclude '/home/nuc/config/*/temp' \
    --exclude '/home/nuc/config/*/.cache' \
    --exclude '/home/nuc/config/*/node_modules' \
    --exclude '/home/nuc/config/*/build' \
    --exclude '/home/nuc/config/*/dist' \
    ::homelab-nuc-{hostname}-{now} \
    /home/nuc/config

# Verify backup integrity
echo "Verifying backup..."
borg check --verify-data --last 1

echo "Local config backup completed successfully!"
```

**Script 2: Remote Full Backup**
```bash
# /usr/local/bin/borg-backup-remote-full.sh
#!/bin/bash

set -euo pipefail

export BORG_REPO=/mnt/hetzner/homelab-backup
export BORG_PASSPHRASE='${borg_passphrase_hetzner}'

# Ensure Hetzner is mounted
if ! mountpoint -q /mnt/hetzner; then
    echo "Mounting Hetzner Storage Box..."
    sshfs root@storage-xxx.your-box.de:/backups /mnt/hetzner
fi

# Prune old backups (conservative retention)
echo "Pruning old remote backups..."
borg prune -v --list \
    --keep-weekly=8 \
    --keep-monthly=12 \
    --keep-yearly=3

# Create full backup
echo "Creating full remote backup (this may take several hours)..."
borg create \
    --info \
    --stats \
    --compression lz4 \
    --exclude-caches \
    --exclude '/home/nuc/config/*/cache' \
    --exclude '/home/nuc/config/*/logs' \
    --exclude '/home/nuc/config/*/temp' \
    --exclude '/home/nuc/config/*/.cache' \
    --exclude '/home/nuc/config/*/node_modules' \
    --exclude '/home/nuc/config/*/build' \
    --exclude '/home/nuc/config/*/dist' \
    --exclude '/tank/timemachine/*/Cache' \
    ::homelab-nuc-{hostname}-{now} \
    /home/nuc/config \
    /tank/medien \
    /tank/immich \
    /tank/ai-models \
    /tank/config \
    /tank/timemachine

# Verify backup
echo "Verifying backup..."
borg check --verify-data --last 1

# Unmount Hetzner
fusermount -u /mnt/hetzner

echo "Remote full backup completed successfully!"
```

**Script 3: Full System Backup (First Time)**
```bash
# /usr/local/bin/borg-backup-initial-full.sh
#!/bin/bash

set -euo pipefail

export BORG_REPO=/mnt/hetzner/homelab-backup
export BORG_PASSPHRASE='${borg_passphrase_hetzner}'

# Mount Hetzner
sshfs root@storage-xxx.your-box.de:/backups /mnt/hetzner

echo "Starting INITIAL full backup (this will take 24-48 hours)..."
echo "Please ensure stable internet connection and power..."

# Create initial backup
borg create \
    --info \
    --stats \
    --compression lz4 \
    --exclude-caches \
    --exclude '/home/nuc/config/*/cache' \
    --exclude '/home/nuc/config/*/logs' \
    --exclude '/home/nuc/config/*/temp' \
    --exclude '/home/nuc/config/*/.cache' \
    --exclude '/home/nuc/config/*/node_modules' \
    --exclude '/home/nuc/config/*/build' \
    --exclude '/home/nuc/config/*/dist' \
    --exclude '/tank/timemachine/*/Cache' \
    ::homelab-nuc-{hostname}-{now} \
    /home/nuc/config \
    /tank/medien \
    /tank/immich \
    /tank/ai-models \
    /tank/config \
    /tank/timemachine

# Verify
echo "Verifying initial backup..."
borg check --verify-data

fusermount -u /mnt/hetzner
echo "Initial full backup completed!"
```

### Phase 6: Cron Automation

**Add to /etc/cron.d/borg-backups on homelab-nuc**:
```bash
# Local config backups (daily at 2 AM)
0 2 * * * root /usr/local/bin/borg-backup-local-configs.sh >> /var/log/borg-local.log 2>&1

# Remote full backups (weekly Sunday at 1 AM)
0 1 * * 0 root /usr/local/bin/borg-backup-remote-full.sh >> /var/log/borg-remote.log 2>&1

# Remote initial backup (run once, manual)
# 0 1 * * 1 root /usr/local/bin/borg-backup-initial-full.sh >> /var/log/borg-initial.log 2>&1
```

**Log Rotation**:
```bash
# /etc/logrotate.d/borg-backups
/var/log/borg-*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    create 0640 root root
}
```

### Phase 7: Testing & Verification

**Test Local Backup**:
```bash
# Run manually
/usr/local/bin/borg-backup-local-configs.sh

# List backups
borg list /tank/backups/homelab-configs

# Test restore
mkdir -p /tmp/test-restore
cd /tmp/test-restore
borg extract /tank/backups/homelab-configs::homelab-nuc-20241116-020000 home/nuc/config/home-assistant
ls -la /tmp/test-restore/home/nuc/config/home-assistant

# Cleanup
rm -rf /tmp/test-restore
```

**Test Remote Backup**:
```bash
# Run during off-peak hours
/usr/local/bin/borg-backup-remote-full.sh

# List backups
borg list /mnt/hetzner/homelab-backup

# Test restore (small subset)
mkdir -p /tmp/test-restore-remote
cd /tmp/test-restore-remote
borg extract /mnt/hetzner/homelab-backup::homelab-nuc-20241116-010000 home/nuc/config/home-assistant
ls -la /tmp/test-restore-remote/home/nuc/config/home-assistant
rm -rf /tmp/test-restore-remote
```

**Verify ZFS Snapshots**:
```bash
# Check snapshots exist
zfs list -t snapshot | grep tank

# Test rollback
zfs rollback tank/immich@2024-11-16-0200
```

### Phase 8: Documentation & Recovery Procedures

**Create Recovery Guide**:
```markdown
# Recovery Procedures

## Scenario 1: Config Corruption (Local Fix)

**Problem**: Home Assistant config corrupted

**Solution** (5 minutes):
```bash
# List available backups
borg list /tank/backups/homelab-configs | grep home-assistant

# Extract specific config
cd /tmp
borg extract /tank/backups/homelab-configs::homelab-nuc-20241116-020000 home/nuc/config/home-assistant

# Restore
cp -r /tmp/home/nuc/config/home-assistant /home/nuc/config/

# Restart service
docker restart home-assistant
```

## Scenario 2: Accidental File Delete

**Problem**: Deleted photos from Immich library

**Solution** (30 seconds):
```bash
# List snapshots
zfs list -t snapshot | grep immich

# Find snapshot before deletion
zfs list -t snapshot -o name,used,refer | grep immich

# Rollback
zfs rollback tank/immich@2024-11-15-1000
```

## Scenario 3: Server Death (Full Disaster)

**Problem**: homelab-nuc hardware failure

**Solution** (6-24 hours):
```bash
# 1. Set up new server with Ubuntu
# 2. Install ZFS
# 3. Create pool
zpool create tank mirror /dev/sda /dev/sdb

# 4. Mount Hetzner
sshfs root@storage-xxx.your-box.de:/backups /mnt/hetzner

# 5. Restore from Hetzner
borg extract /mnt/hetzner/homelab-backup::homelab-nuc-20241116-010000

# 6. Import ZFS datasets
zpool import tank

# 7. Restore Docker configs
cp -r /root/home/nuc/config /home/nuc/

# 8. Restart services
cd /home/nuc/config
for dir in */; do
    cd "$dir"
    docker compose up -d
    cd ..
done
```

## Scenario 4: Ransomware Attack

**Problem**: All local data encrypted

**Solution**: Use Hetzner backup (off-site, immutable)
```bash
# Verify backup integrity
borg check /mnt/hetzner/homelab-backup

# Restore to new clean server
sshfs root@storage-xxx.your-box.de:/backups /mnt/hetzner
borg extract /mnt/hetzner/homelab-backup::homelab-nuc-20241116-010000
```

## Scenario 5: Partial Data Recovery

**Problem**: Need specific file from days ago

**Solution**:
```bash
# List all versions of file
borg list /tank/backups/homelab-configs | grep "home-assistant/configuration.yaml"

# Extract specific version
borg extract /tank/backups/homelab-configs::homelab-nuc-20241115-020000 home/nuc/config/home-assistant/configuration.yaml
```

## Scenario 6: Verify Backup Health

**Monthly health check**:
```bash
# Check Borg repositories
borg check /tank/backups/homelab-configs
borg check /mnt/hetzner/homelab-backup

# Check ZFS pool
zpool status tank
zpool scrub tank

# Check snapshot retention
zfs list -t snapshot | wc -l
# Should be ~47 snapshots (24h + 7d + 4w + 12m)
```

## Scenario 7: Encryption Key Recovery

**Problem**: Lost Borg passphrase

**Solution**:
- Recovery key is stored in repository (use `repokey` mode)
- Run `borg info` to see key location
- Export key: `borg key export /repo backup-key.txt`
- Store this key securely (e.g., password manager)
```

## Ansible Integration

### Create Borg Role

**roles/borg/tasks/main.yml**:
```yaml
---
- name: Install BorgBackup
  apt:
    name: borgbackup
    state: present
    update_cache: yes

- name: Create backup directories
  file:
    path: "{{ item }}"
    state: directory
    mode: '0750'
    owner: "{{ ansible_user_id }}"
    group: "{{ ansible_user_id }}"
  loop:
    - /tank/backups
    - /mnt/hetzner

- name: Create backup scripts
  template:
    src: "{{ item.name }}.j2"
    dest: "{{ item.dest }}"
    mode: '0750'
    owner: root
    group: root
  loop:
    - { name: borg-backup-local-configs, dest: /usr/local/bin/borg-backup-local-configs.sh }
    - { name: borg-backup-remote-full, dest: /usr/local/bin/borg-backup-remote-full.sh }
    - { name: borg-backup-initial-full, dest: /usr/local/bin/borg-backup-initial-full.sh }

- name: Set up cron jobs
  cron:
    name: "{{ item.name }}"
    minute: "{{ item.minute }}"
    hour: "{{ item.hour }}"
    weekday: "{{ item.weekday | default('*') }}"
    job: "{{ item.job }}"
    user: root
    state: present
  loop:
    - name: "Local config backup"
      minute: "0"
      hour: "2"
      job: "/usr/local/bin/borg-backup-local-configs.sh >> /var/log/borg-local.log 2>&1"
    - name: "Remote full backup"
      minute: "0"
      hour: "1"
      weekday: "0"
      job: "/usr/local/bin/borg-backup-remote-full.sh >> /var/log/borg-remote.log 2>&1"
```

**roles/borg/templates/borg-backup-local-configs.sh.j2**:
```bash
#!/bin/bash

set -euo pipefail

export BORG_REPO=/tank/backups/homelab-configs
export BORG_PASSPHRASE='{{ borg_passphrase }}'

LOG_FILE="/var/log/borg-local-$(date +%Y%m%d).log"

echo "$(date): Starting local config backup" >> "$LOG_FILE"

# Prune old backups
echo "Pruning old local backups..." | tee -a "$LOG_FILE"
borg prune -v --list \
    --keep-hourly=24 \
    --keep-daily=7 \
    --keep-weekly=4 \
    --keep-monthly=12 2>&1 | tee -a "$LOG_FILE"

# Create backup
echo "Creating local config backup..." | tee -a "$LOG_FILE"
borg create \
    --info \
    --stats \
    --compression lz4 \
    --exclude-caches \
    --exclude '/home/nuc/config/*/cache' \
    --exclude '/home/nuc/config/*/logs' \
    --exclude '/home/nuc/config/*/temp' \
    --exclude '/home/nuc/config/*/.cache' \
    --exclude '/home/nuc/config/*/node_modules' \
    --exclude '/home/nuc/config/*/build' \
    --exclude '/home/nuc/config/*/dist' \
    ::homelab-nuc-{hostname}-{now} \
    /home/nuc/config 2>&1 | tee -a "$LOG_FILE"

# Verify backup
echo "Verifying backup..." | tee -a "$LOG_FILE"
borg check --verify-data --last 1 2>&1 | tee -a "$LOG_FILE"

echo "$(date): Local config backup completed successfully" >> "$LOG_FILE"
```

### Add to setup.yml

**setup.yml**:
```yaml
  hosts: homelab
  roles:
    - geerlingguy.docker
    - basic
    - glances
    - caddy
    - pihole
    - homepage
    - home-assistant
    - monitoring
    - borg  # Add this
```

### Variables

**group_vars/homelab.yml**:
```yaml
# Borg backup configuration
borg_passphrase: "{{ vault_borg_passphrase }}"
borg_passphrase_hetzner: "{{ vault_borg_passphrase_hetzner }}"

# Hetzner Storage Box
hetzner_host: "storage-xxx.your-box.de"
hetzner_user: "root"
hetzner_path: "/backups"

# Backup paths
backup_local_repo: "/tank/backups/homelab-configs"
backup_remote_repo: "/mnt/hetzner/homelab-backup"
```

**group_vars/all/secrets.yml** (encrypted with ansible-vault):
```yaml
vault_borg_passphrase: "your-strong-local-passphrase"
vault_borg_passphrase_hetzner: "your-strong-remote-passphrase"
vault_hetzner_password: "your-hetzner-ssh-password"
```

## Estimated Costs

### Hetzner Storage Box
- **1TB**: €4.90/month
- **10TB**: €34.90/month
- **20TB**: €69.90/month

For 6TB data: €34.90/month

### Bandwidth
- **Initial backup**: 6TB upload (2-3 days)
- **Incremental**: ~100-500GB/week (depending on changes)
- **Monthly**: ~1-2TB (config + photos + media changes)

## Key Takeaways

1. **Three-tier strategy** provides maximum protection
2. **Local Borg** for fast config restores (5 minutes)
3. **Remote Borg** for complete disaster recovery
4. **ZFS snapshots** for instant rollback (30 seconds)
5. **Encryption** by default (repokey)
6. **Deduplication** saves bandwidth and storage
7. **Automation** via cron ensures backups run

## Next Steps

1. Review and approve this plan
2. Gather Hetzner Storage Box credentials
3. Create strong passphrases for Borg encryption
4. Implement in Ansible (borg role + cron jobs)
5. Run initial full backup (off-peak hours)
6. Test all recovery scenarios
7. Document all passkeys in secure location

## Reference Commands

```bash
# List backups
borg list /tank/backups/homelab-configs
borg list /mnt/hetzner/homelab-backup

# Backup info
borg info /tank/backups/homelab-configs
borg info /mnt/hetzner/homelab-backup

# Check integrity
borg check /tank/backups/homelab-configs
borg check --verify-data /mnt/hetzner/homelab-backup

# Prune old backups
borg prune /tank/backups/homelab-configs
borg prune /mnt/hetzner/homelab-backup

# Extract backup
cd /tmp
borg extract /tank/backups/homelab-configs::homelab-nuc-20241116-020000 home/nuc/config/home-assistant

# Mount backup (read-only access)
borg mount /tank/backups/homelab-configs /mnt/borg-mount
```

---

**Status**: Ready for Implementation
**Owner**: Homelab Infrastructure
**Review Date**: Monthly
**Last Updated**: 2024-11-16