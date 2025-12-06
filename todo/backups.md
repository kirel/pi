# Homelab Backup Strategy - Final Implementation Plan

## Overview

**Three-tier backup strategy** combining ZFS snapshots, local Borg, and remote Borg to Remote Backup Location.

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
│  Tier 2: Borgmatic (local)              │
│  ✅ IMPLEMENTED                          │
│  └── /tank/backups/homelab-configs      │
│      └── Only service configs           │
│                                         │
│  Tier 3: Borg (remote)                  │
│  ⏳ PENDING                              │
│      └── Remote Backup Location             │
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
| **Server death** | Borg Remote | 6-24 hours | Everything |
| **Ransomware** | Borg Remote | 6-24 hours | Everything (off-site) |

## Remote Backup Destination Requirements (Tier 3)

The "Tier 3" remote backup is designed to be location-agnostic. While the documentation often refers to a "Remote Backup Location" or a "Remote NAS," any remote machine can serve as a backup destination, provided it meets two simple prerequisites:

1.  **SSH Access**: The backup source machine (`homelab-nuc`) must be able to connect to the remote destination via SSH, preferably using key-based authentication for security and automation.
2.  **Borg Installation**: The `borg` binary must be installed on the remote destination. The version should be compatible with the Borg version running on the source machine.

This flexibility means a dedicated storage service (like Hetzner) or a self-managed server (e.g., a NAS located at a family member's house) are both equally viable options. The connection is handled directly through Borg's native SSH support (`ssh://user@host:port/path/to/repo`), which is configured in the `borgmatic` configuration file (`config-remote.yaml`).

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

**Remote Borg Repository (Remote Backup Location)**
```
Remote Backup Location: homelab-backup/
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

### Phase 2: Install Borgmatic on All Hosts

This plan is updated to use `borgmatic`, a configuration-driven wrapper for Borg that simplifies management and improves robustness.

**Action**: Create a dedicated Ansible role `roles/borgmatic`.

```yaml
# Example task in roles/borgmatic/tasks/main.yml
- name: Install Borgmatic and dependencies
  apt:
    name:
      - borgmatic
      - sshfs  # Still useful for manual restores
    state: present
    update_cache: yes
```

### Phase 3: Create Local Borg Repository

After the Ansible role has created the necessary directories and config files (see Phase 8), initialize the repository.

**On `homelab-nuc`**:
```bash
# Initialize repository with encryption using the borgmatic config
sudo borgmatic --config /etc/borgmatic.d/config-local.yaml init --encryption repokey

# Set permissions (adjust if your user differs)
sudo chown -R nuc:nuc /tank/backups/homelab-configs
```

### Phase 4: Create Remote Borg Repository

**Pre-requisite**: Ensure the `root` user on `homelab-nuc` can SSH into the Remote Backup Location using key-based authentication. The `distribute_ssh_key.yml` playbook can be adapted for this.

**Initialize remote repository**:
```bash
# Initialize on Hetzner via borgmatic's native SSH support
sudo borgmatic --config /etc/borgmatic.d/config-remote.yaml init --encryption repokey
```
This method is more secure and direct than using SSHFS for backups.

### Phase 5: Configure Borgmatic

We will create two configuration files in `/etc/borgmatic.d/`, managed by Ansible. This approach replaces the legacy shell scripts.

1.  **`config-local.yaml`**: For frequent, fast backups of local service configurations.
2.  **`config-remote.yaml`**: For comprehensive, off-site backups of all critical data.

The full structure of these files is detailed in the Ansible integration section below.

### Phase 6: Automation with Systemd Timers

We'll use systemd timers for more robust and manageable execution over traditional cron jobs. Logging is automatically handled by `journald`.

**Systemd Units (deployed via Ansible):**
*   `/etc/systemd/system/borgmatic-local.service` & `borgmatic-local.timer`
*   `/etc/systemd/system/borgmatic-remote.service` & `borgmatic-remote.timer`

**Timer Schedule:**
*   **Local**: Runs daily.
*   **Remote**: Runs weekly.

**Management Commands:**
```bash
# Enable and start the timers
sudo systemctl enable --now borgmatic-local.timer
sudo systemctl enable --now borgmatic-remote.timer

# Check logs at any time
journalctl -u borgmatic-local.service
journalctl -u borgmatic-remote.service
```

### Phase 7: Testing & Verification

**Test Local Backup**:
```bash
# Run a backup manually
sudo borgmatic --config /etc/borgmatic.d/config-local.yaml create --verbosity 1

# List archives to confirm success
sudo borgmatic --config /etc/borgmatic.d/config-local.yaml list

# Test a restore
mkdir -p /tmp/test-restore
cd /tmp/test-restore
sudo borgmatic --config /etc/borgmatic.d/config-local.yaml extract --archive LATEST --path /home/nuc/config/homepage
ls -la /tmp/test-restore/home/nuc/config/homepage
rm -rf /tmp/test-restore
```

**Test Remote Backup**:
```bash
# Run a backup manually (best during off-peak hours)
sudo borgmatic --config /etc/borgmatic.d/config-remote.yaml create --verbosity 1

# List archives
sudo borgmatic --config /etc/borgmatic.d/config-remote.yaml list

# Test a small restore
mkdir -p /tmp/test-restore-remote
cd /tmp/test-restore-remote
sudo borgmatic --config /etc/borgmatic.d/config-remote.yaml extract --archive LATEST --path /home/nuc/config/caddy
ls -la /tmp/test-restore-remote/home/nuc/config/caddy
rm -rf /tmp/test-restore-remote
```

### Phase 8: Documentation & Recovery Procedures

**(This section should be updated to use `borgmatic` commands, e.g., `sudo borgmatic list ...`, `sudo borgmatic extract ...`)**

... (Recovery procedures remain conceptually the same) ...

## Ansible Integration (Borgmatic)

The new `borgmatic` role will handle the entire setup.

### Create Borgmatic Role

**`roles/borgmatic/tasks/main.yml`**:
```yaml
---
- name: Install Borgmatic and dependencies
  apt:
    name: ['borgmatic', 'sshfs']
    state: present
    update_cache: yes

- name: Create borgmatic configuration directory
  file:
    path: /etc/borgmatic.d
    state: directory
    mode: '0755'
    owner: root
    group: root

- name: Deploy borgmatic configurations
  template:
    src: "{{ item.name }}.j2"
    dest: "/etc/borgmatic.d/{{ item.name }}"
    mode: '0600' # Encrypted vars are templated here
    owner: root
    group: root
  loop:
    - { name: config-local.yaml }
    - { name: config-remote.yaml }
  notify: Reload systemd daemon

- name: Deploy systemd service units
  copy:
    src: "{{ item }}"
    dest: "/etc/systemd/system/{{ item }}"
    mode: '0644'
  loop:
    - borgmatic-local.service
    - borgmatic-remote.service
  notify: Reload systemd daemon

- name: Deploy systemd timer units
  copy:
    src: "{{ item }}"
    dest: "/etc/systemd/system/{{ item }}"
    mode: '0644'
  loop:
    - borgmatic-local.timer
    - borgmatic-remote.timer
  notify: Reload systemd daemon

- name: Flush handlers to apply systemd changes
  meta: flush_handlers

- name: Enable and start borgmatic timers
  systemd:
    name: "{{ item }}"
    enabled: yes
    state: started
  loop:
    - borgmatic-local.timer
    - borgmatic-remote.timer
```

**`roles/borgmatic/handlers/main.yml`**:
```yaml
---
- name: Reload systemd daemon
  systemd:
    daemon_reload: yes
```

**`roles/borgmatic/templates/config-local.yaml.j2`**:
```yaml
location:
    source_directories:
        - /home/nuc/config

    repositories:
        - path: {{ backup_local_repo }}

    exclude_patterns:
        - '**/cache'
        - '**/logs'
        - '**/temp'
        - '**/.cache'
        - '**/node_modules'
        - '**/build'
        - '**/dist'

storage:
    encryption_passphrase: '{{ borg_passphrase }}'
    compression: lz4
    archive_name_format: 'homelab-nuc-{hostname}-{now}'

retention:
    keep_hourly: 24
    keep_daily: 7
    keep_weekly: 4
    keep_monthly: 12
    prefix: 'homelab-nuc-{hostname}-'

consistency:
    checks:
        - repository
        - archives
    check_last: 1
    prefix: 'homelab-nuc-{hostname}-'
```

**`roles/borgmatic/templates/config-remote.yaml.j2`**:
```yaml
location:
    source_directories:
        - /home/nuc/config
        - /tank/medien
        - /tank/immich
        - /tank/config
        - /tank/timemachine

    repositories:
        - path: '{{ remote_backup_user }}@{{ remote_backup_host }}:{{ remote_backup_repo_path }}'

    exclude_patterns:
        - '**/cache'
        - '**/logs'
        - '**/temp'
        - '**/.cache'
        - '**/node_modules'
        - '**/build'
        - '**/dist'
        - '/tank/timemachine/*/Cache'

storage:
    encryption_passphrase: '{{ vault_borg_passphrase }}'
    compression: lz4
    archive_name_format: 'homelab-nuc-{hostname}-{now}'

retention:
    keep_weekly: 8
    keep_monthly: 12
    keep_yearly: 3
    prefix: 'homelab-nuc-{hostname}-'

consistency:
    checks:
        - repository
        - archives
    check_last: 1
    prefix: 'homelab-nuc-{hostname}-'

hooks:
    before_backup:
        - echo "Starting remote backup..."
    after_backup:
        - echo "Remote backup complete."
    on_error:
        - echo "Error during remote backup!"
```

(The systemd unit files would be placed in `roles/borgmatic/files/`)

### Add to setup.yml

**setup.yml**:
```yaml
  hosts: homelab
  roles:
    # ... other roles
    - borgmatic  # Add this
```

### Variables

**group_vars/homelab.yml**:
```yaml
# Borgmatic backup configuration
backup_local_repo: "/tank/backups/homelab-configs"

# Remote Backup Location
hetzner_host: "uXXXXX.your-server.de"
hetzner_user: "uXXXXX"
```

**group_vars/all/secrets.yml** (encrypted with ansible-vault):
```yaml
vault_borg_passphrase: "your-strong-passphrase"
```

## Estimated Costs
(This section remains unchanged)

## Key Takeaways

1.  **Three-tier strategy** provides maximum protection.
2.  **Borgmatic** simplifies and automates local and remote backups.
3.  **Systemd timers** provide robust, manageable scheduling.
4.  **ZFS snapshots** for instant rollback (30 seconds).
5.  **Encryption** is handled seamlessly by Borgmatic.
6.  **Deduplication** saves significant bandwidth and storage.

## Next Steps

1.  Review and approve this updated plan.
2.  Create and populate the `borgmatic` Ansible role.
3.  Gather Remote Backup Location credentials and configure SSH keys.
4.  Create strong passphrases and store them in Ansible Vault.
5.  Deploy the role to the `homelab-nuc`.
6.  Run the `init` commands for both repositories.
7.  Run the "Test & Verification" steps.
8.  Update the recovery guide with `borgmatic` commands.

## Reference Commands (`borgmatic`)

```bash
# Run a specific backup
borgmatic --config /etc/borgmatic.d/config-local.yaml create

# List archives in a repository
borgmatic --config /etc/borgmatic.d/config-local.yaml list

# Show info about a repository
borgmatic --config /etc/borgmatic.d/config-local.yaml info

# Check repository integrity
borgmatic --config /etc/borgmatic.d/config-remote.yaml check

# Prune old archives
borgmatic --config /etc/borgmatic.d/config-local.yaml prune

# Extract a file/directory from the latest archive
cd /tmp/restore
borgmatic -c /etc/borgmatic.d/config-local.yaml extract --archive LATEST --path /home/nuc/config/homepage

# Mount a repository for browsing
mkdir /mnt/borg-mount
borgmatic -c /etc/borgmatic.d/config-local.yaml mount --mount-point /mnt/borg-mount
# ... do stuff ...
umount /mnt/borg-mount
```

## ✅ Implementation Status

### **COMPLETED**
- ✅ **Tier 2**: Borgmatic local backup system (2025-12-04)
  - Ansible role: `roles/borgmatic/`
  - Integration: Added to `setup.yml`
  - Configuration: `group_vars/homelab.yml`
  - Automation: systemd timer (daily)
  - Deployment: `uv run ansible-playbook setup.yml --tags borgmatic --limit homelab`

### **REMAINING**
- ⏳ **Tier 3**: Remote backup (Remote Backup Location)
  - Add `config-remote.yaml.j2` template
  - Add remote systemd service/timer
  - Configure Hetzner/NAS SSH credentials
  - Test remote backup

### **POST-DEPLOYMENT STEPS** (Required before first run)
1. Add encryption passphrase to `group_vars/all/secrets.yml`:
   ```bash
   uv run ansible-vault encrypt_string 'your-strong-passphrase' --name 'vault_borg_passphrase'
   ```

2. Initialize repositories on homelab-nuc:
   ```bash
   # Initialize local repository
   sudo borgmatic --config /etc/borgmatic.d/config-local.yaml init --encryption repokey
   sudo systemctl enable --now borgmatic-local.timer

   # Initialize remote repository (once configured)
   # sudo borgmatic --config /etc/borgmatic.d/config-remote.yaml init --encryption repokey
   # sudo systemctl enable --now borgmatic-remote.timer
   ```

3. Test backup:
   ```bash
   sudo borgmatic --config /etc/borgmatic.d/config-local.yaml create --verbosity 1
   sudo borgmatic --config /etc/borgmatic.d/config-local.yaml list
   ```

---

**Status**: ✅ Tier 2 Complete | ⏳ Tier 3 Pending
**Owner**: Homelab Infrastructure
**Review Date**: Monthly
**Last Updated**: 2025-12-04
