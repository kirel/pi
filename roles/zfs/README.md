# ZFS Role

Ansible role for managing ZFS pools and datasets on Ubuntu-based homelab servers.

## Features

- ✅ Install ZFS utilities and kernel modules
- ✅ Create ZFS pools with optimal settings for NAS use
- ✅ Manage datasets with custom properties
- ✅ Automated monthly scrub scheduling
- ✅ Optional snapshot management with Sanoid
- ✅ Support for single-disk to mirror conversion

## Requirements

- Ubuntu 20.04+ (Focal or Jammy)
- Root access
- Ansible 2.9+

## Role Variables

### Pool Configuration

```yaml
zfs_pool_name: tank                    # Name of the ZFS pool
zfs_pool_state: present                # present or absent
zfs_pool_devices:                      # Initial devices (use by-id paths)
  - /dev/disk/by-id/ata-WDC_WD60EZAX-00C8VB0_WD-WX52DC3JW19P

zfs_pool_properties:
  ashift: 12                           # 4K sector alignment
  autoexpand: "on"                     # Auto-expand with larger disks

zfs_root_properties:
  compression: lz4                     # Fast compression
  atime: "off"                         # Disable access time updates
  xattr: sa                            # Extended attributes in system area
  acltype: posixacl                    # POSIX ACLs
  relatime: "on"                       # Relative access time
```

### Dataset Configuration

```yaml
zfs_datasets:
  - name: "{{ zfs_pool_name }}/medien"
    properties:
      mountpoint: /tank/medien
      recordsize: 128K                 # Optimal for large files
      compression: lz4
    owner: "{{ username }}"
    group: users
    mode: "0775"
```

### Scrub Configuration

```yaml
zfs_scrub_enabled: true
zfs_scrub_schedule:
  minute: "0"
  hour: "2"
  day: "1-7"
  weekday: "0"                         # Sunday at 2 AM
```

### Snapshot Configuration (Optional)

```yaml
zfs_snapshots_enabled: false           # Enable Sanoid snapshots
zfs_snapshot_schedule:
  hourly: 24
  daily: 7
  weekly: 4
  monthly: 12
```

## Usage

### Initial Setup (Single Disk)

1. Add the role to your playbook:

```yaml
- hosts: homelab
  roles:
    - role: zfs
      tags: zfs
```

2. Deploy:

```bash
uv run ansible-playbook setup.yml --tags zfs --limit homelab
```

### Converting to Mirror (When Second Drive Arrives)

After the second 6TB drive is installed:

```bash
# SSH to the server
ssh root@homelab-nuc.lan

# Attach second drive as mirror
zpool attach tank \
  /dev/disk/by-id/ata-WDC_WD60EZAX-00C8VB0_WD-WX52DC3JW19P \
  /dev/disk/by-id/ata-WDC_WD60EZAX-XXXXXXXX_WD-XXXXXXXXXXXX

# Monitor resilver progress
zpool status tank
```

The resilver will copy all data to the second drive, creating a mirror.

### Data Migration from Old Drive

To migrate data from `/mnt/Medien` (2TB Seagate) to ZFS:

```bash
# Use rsync for safe, resumable transfer
rsync -avhP --delete /mnt/Medien/ /tank/medien/

# Verify data integrity
diff -r /mnt/Medien/ /tank/medien/

# Update mount in storage role or fstab
# Then unmount old drive
umount /mnt/Medien
```

## Maintenance Commands

### Check Pool Status
```bash
zpool status tank
zpool list tank
```

### Manual Scrub
```bash
zpool scrub tank
```

### View Scrub History
```bash
zpool history tank | grep scrub
cat /var/log/zfs-scrub.log
```

### Dataset Management
```bash
# List all datasets
zfs list

# Get dataset properties
zfs get all tank/medien

# Create snapshot manually
zfs snapshot tank/medien@backup-$(date +%Y%m%d)

# List snapshots
zfs list -t snapshot
```

## Integration with Existing Storage Role

Update your `storage` role to use ZFS paths:

```yaml
# In roles/storage/tasks/main.yml
volumes:
  - /tank/medien:/shares/Medien        # Changed from /mnt/Medien
  - /tank/config:/shares/config        # Changed from {{ config_root }}
  - /tank/timemachine:/shares/dreifuenf/timemachine
```

## Troubleshooting

### Pool won't import
```bash
zpool import -f tank
```

### Check for errors
```bash
zpool status -v tank
dmesg | grep -i zfs
```

### Performance tuning
```bash
# Check ARC stats
cat /proc/spl/kstat/zfs/arcstats

# Adjust ARC size (in /etc/modprobe.d/zfs.conf)
options zfs zfs_arc_max=8589934592  # 8GB
```

## Best Practices

1. **Always use `/dev/disk/by-id/` paths** - More reliable than `/dev/sdX`
2. **Enable scrubs** - Monthly scrubs detect silent data corruption
3. **Monitor pool health** - Set up alerts for degraded pools
4. **Test restores** - Verify snapshots can be restored
5. **Document drive serial numbers** - Track which physical drive is which

## Performance Expectations

With your WD Blue 6TB drives (5400 RPM, CMR):
- **Sequential read:** ~150-180 MB/s
- **Sequential write:** ~150-180 MB/s (single disk), ~150 MB/s (mirror)
- **Random I/O:** Adequate for media streaming and file serving
- **Compression ratio:** Typically 1.2-1.5x for media files

## Security Notes

- ZFS datasets inherit permissions from mountpoint
- Use `zfs allow` for delegated administration
- Consider encryption for sensitive data: `zfs create -o encryption=on`

## License

MIT

## Author

Homelab Infrastructure Team
