# ZFS Migration Guide for homelab-nuc

This guide walks you through migrating from your current 2TB Seagate drive to a ZFS mirror with two 6TB WD Blue drives.

## Current State

- **System Drive:** 1TB SanDisk SSD (`/dev/sda`) - Ubuntu system
- **Data Drive 1:** 6TB WD Blue (`/dev/sdb`) - **UNUSED, brand new**
- **Data Drive 2:** 2TB Seagate (`/dev/sdc`) - Currently mounted at `/mnt/Medien` with data
- **Future:** Second 6TB WD Blue arriving later

## Migration Strategy

### Phase 1: Create ZFS Pool (Do Now)

1. **Deploy ZFS role**
2. **Create single-disk pool** on first 6TB drive
3. **Migrate data** from 2TB to ZFS
4. **Update storage role** to use ZFS paths
5. **Verify everything works**

### Phase 2: Add Mirror (When 2nd Drive Arrives)

6. **Install second 6TB drive** (replaces 2TB physically)
7. **Attach as mirror** to existing pool
8. **Wait for resilver** to complete

---

## Phase 1: Detailed Steps

### Step 1: Get Disk IDs

First, identify the exact disk-by-id paths (more reliable than /dev/sdX):

```bash
ssh root@homelab-nuc.lan
ls -la /dev/disk/by-id/ | grep -E 'WD60EZAX|ST2000'
```

Expected output:
```
ata-WDC_WD60EZAX-00C8VB0_WD-WX52DC3JW19P -> ../../sdb
ata-ST2000LM007-1R8174_WDZANC70 -> ../../sdc
```

### Step 2: Update ZFS Role Configuration

Edit the ZFS role defaults to use the correct disk ID:

```bash
# Edit locally
nano ~/code/pi/roles/zfs/defaults/main.yml
```

Update the `zfs_pool_devices` line with your actual disk ID from Step 1.

### Step 3: Syntax Check

```bash
cd ~/code/pi
uv run ansible-playbook setup.yml --syntax-check
```

### Step 4: Dry Run

```bash
uv run ansible-playbook setup.yml --tags zfs --limit homelab --check --diff
```

### Step 5: Deploy ZFS

```bash
uv run ansible-playbook setup.yml --tags zfs --limit homelab
```

This will:
- Install ZFS utilities
- Create pool named `tank` on `/dev/sdb`
- Create datasets: `/tank/medien`, `/tank/config`, `/tank/timemachine`, `/tank/backups`
- Set up monthly scrub cron job

### Step 6: Verify ZFS Pool

```bash
ssh root@homelab-nuc.lan

# Check pool status
zpool status tank
zpool list tank

# Check datasets
zfs list

# Check mount points
df -h | grep tank
```

Expected output:
```
NAME                SIZE  ALLOC   FREE
tank               5.45T   104K  5.45T
tank/medien        5.45T   104K  5.45T
tank/config        5.45T   104K  5.45T
tank/timemachine   5.45T   104K  5.45T
tank/backups       5.45T   104K  5.45T
```

### Step 7: Migrate Data from 2TB to ZFS

Use rsync for safe, resumable transfer:

```bash
ssh root@homelab-nuc.lan

# Check current data size
du -sh /mnt/Medien

# Start migration (this may take hours depending on data size)
rsync -avhP --delete /mnt/Medien/ /tank/medien/

# Verify data integrity
diff -r /mnt/Medien/ /tank/medien/
```

**Note:** The trailing slashes in rsync are important!
- `/mnt/Medien/` = copy contents
- `/mnt/Medien` = copy directory itself

### Step 8: Update Storage Role

Edit the storage role to use ZFS paths:

```bash
nano ~/code/pi/roles/storage/tasks/main.yml
```

Find the Samba volume mounts and update:

```yaml
volumes:
  - /etc/avahi/services/:/external/avahi
  - /tank/medien:/shares/Medien          # Changed from /mnt/Medien
  - /tank/timemachine:/shares/dreifuenf  # Changed from /mnt/dreifuenf
  - "{{ config_root }}:/shares/config"
```

Also update Syncthing volumes:

```yaml
volumes:
  - "{{ syncthing_config_folder }}:/config"
  - "{{ syncthing_data_folder }}:/data"
  - /tank/medien:/Medien                 # Changed from /mnt/Medien
  - /tank/timemachine:/dreifuenf         # Changed if needed
```

### Step 9: Redeploy Storage Services

```bash
uv run ansible-playbook setup.yml --tags storage --limit homelab
```

### Step 10: Test Everything

```bash
# Check Samba is running
ssh root@homelab-nuc.lan "docker ps | grep samba"

# Check Syncthing is running
ssh root@homelab-nuc.lan "docker ps | grep syncthing"

# Test Samba access from your Mac/PC
# Try accessing \\homelab-nuc.lan\Medien or smb://homelab-nuc.lan/Medien

# Check Syncthing web UI
# Open https://syncthing-homelab.lan
```

### Step 11: Unmount Old Drive (Optional - Keep as Backup)

Once everything is verified working:

```bash
ssh root@homelab-nuc.lan

# Unmount the old 2TB drive
umount /mnt/Medien

# Comment out in fstab (if it's there)
nano /etc/fstab
# Add # in front of the Medien line

# Or remove the mount entirely from storage role
```

**Recommendation:** Keep the 2TB drive mounted read-only as a backup for a few weeks:

```bash
mount -o ro /dev/sdc2 /mnt/Medien-backup
```

---

## Phase 2: Add Mirror (When 2nd Drive Arrives)

### Step 1: Physical Installation

1. Shut down homelab-nuc
2. Remove 2TB Seagate drive
3. Install second 6TB WD Blue drive
4. Boot up

### Step 2: Identify New Drive

```bash
ssh root@homelab-nuc.lan

# Find the new drive's by-id path
ls -la /dev/disk/by-id/ | grep WD60EZAX

# Should see two WD drives now
```

### Step 3: Attach as Mirror

```bash
# Attach second drive to create mirror
zpool attach tank \
  /dev/disk/by-id/ata-WDC_WD60EZAX-00C8VB0_WD-WX52DC3JW19P \
  /dev/disk/by-id/ata-WDC_WD60EZAX-XXXXXXXX_WD-XXXXXXXXXXXX

# Replace XXXXXXXX with actual serial from Step 2
```

### Step 4: Monitor Resilver

The resilver process will copy all data to the second drive:

```bash
# Watch progress
watch -n 5 'zpool status tank'

# Or check periodically
zpool status tank
```

Expected output during resilver:
```
  pool: tank
 state: ONLINE
status: One or more devices is currently being resilvered.
  scan: resilver in progress since Mon Nov 10 22:00:00 2025
        1.2T scanned at 150M/s, 800G issued at 120M/s
        800G resilvered, 66.67% done, 1h30m to go
config:

        NAME                                          STATE
        tank                                          ONLINE
          mirror-0                                    ONLINE
            ata-WDC_WD60EZAX-00C8VB0_WD-WX52DC3JW19P  ONLINE
            ata-WDC_WD60EZAX-XXXXXXXX_WD-XXXXXXXXXXXX ONLINE  (resilvering)
```

### Step 5: Verify Mirror

After resilver completes:

```bash
zpool status tank
```

Expected output:
```
  pool: tank
 state: ONLINE
  scan: resilvered 1.2T in 3h15m with 0 errors
config:

        NAME                                          STATE
        tank                                          ONLINE
          mirror-0                                    ONLINE
            ata-WDC_WD60EZAX-00C8VB0_WD-WX52DC3JW19P  ONLINE
            ata-WDC_WD60EZAX-XXXXXXXX_WD-XXXXXXXXXXXX ONLINE
```

---

## Maintenance

### Monthly Scrub

Automatically runs first Sunday of each month at 2 AM. Check logs:

```bash
cat /var/log/zfs-scrub.log
```

### Manual Scrub

```bash
zpool scrub tank
zpool status tank
```

### Check Pool Health

```bash
# Quick status
zpool status

# Detailed info
zpool list -v tank

# Dataset usage
zfs list -o name,used,avail,refer,mountpoint
```

### Snapshots (Optional)

Enable in `roles/zfs/defaults/main.yml`:

```yaml
zfs_snapshots_enabled: true
```

Then redeploy:

```bash
uv run ansible-playbook setup.yml --tags zfs --limit homelab
```

---

## Troubleshooting

### Pool won't create

```bash
# Check if disk is in use
lsblk
blkid /dev/sdb

# Force creation if needed
zpool create -f tank /dev/disk/by-id/...
```

### Resilver is slow

Normal for 5400 RPM drives. Expected speed: 100-150 MB/s
For 1TB of data: ~2-3 hours

### Pool degraded after reboot

```bash
# Import pool
zpool import tank

# Or force import
zpool import -f tank
```

### Check for errors

```bash
# System logs
dmesg | grep -i zfs
journalctl -u zfs-import-cache.service

# Pool errors
zpool status -v tank
```

---

## Rollback Plan

If something goes wrong:

1. **Data is still on 2TB drive** - Don't delete until verified!
2. **Destroy ZFS pool:**
   ```bash
   zpool destroy tank
   ```
3. **Remount old drive:**
   ```bash
   mount /dev/sdc2 /mnt/Medien
   ```
4. **Redeploy storage role** with old paths

---

## Performance Expectations

### Single Disk (Phase 1)
- Sequential read: ~150-180 MB/s
- Sequential write: ~150-180 MB/s
- Random I/O: Adequate for media streaming

### Mirror (Phase 2)
- Sequential read: ~150-180 MB/s (can read from either disk)
- Sequential write: ~150 MB/s (must write to both disks)
- Random I/O: Improved (can read from both disks)
- **Redundancy:** Can lose one drive without data loss

---

## Next Steps

1. ✅ Review this guide
2. ✅ Run Step 1 to get disk IDs
3. ✅ Update `roles/zfs/defaults/main.yml` with correct disk ID
4. ✅ Deploy ZFS role
5. ✅ Migrate data
6. ✅ Update storage role
7. ✅ Test everything
8. ⏳ Wait for second drive
9. ⏳ Add mirror

---

## Questions?

- Check ZFS role README: `~/code/pi/roles/zfs/README.md`
- ZFS documentation: https://openzfs.github.io/openzfs-docs/
- Ubuntu ZFS guide: https://ubuntu.com/tutorials/setup-zfs-storage-pool

Good luck! 🚀
