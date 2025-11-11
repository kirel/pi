# ZFS Quick Reference

## 🚀 Quick Start Commands

### Deploy ZFS Role
```bash
cd ~/code/pi
uv run ansible-playbook setup.yml --tags zfs --limit homelab
```

### Check Pool Status
```bash
ssh root@homelab-nuc.lan "zpool status tank"
```

### Migrate Data
```bash
ssh root@homelab-nuc.lan "rsync -avhP --delete /mnt/Medien/ /tank/medien/"
```

### Add Mirror (when 2nd drive arrives)
```bash
ssh root@homelab-nuc.lan
zpool attach tank \
  /dev/disk/by-id/ata-WDC_WD60EZAX-00C8VB0_WD-WX52DC3JW19P \
  /dev/disk/by-id/ata-WDC_WD60EZAX-XXXXXXXX_WD-XXXXXXXXXXXX
```

## 📊 Common ZFS Commands

| Command | Description |
|:--------|:------------|
| `zpool status` | Show pool health |
| `zpool list` | List all pools |
| `zfs list` | List all datasets |
| `zpool scrub tank` | Start data integrity check |
| `zfs get all tank/medien` | Show dataset properties |
| `zfs snapshot tank/medien@backup` | Create snapshot |
| `zfs list -t snapshot` | List snapshots |
| `df -h \| grep tank` | Show disk usage |

## 🔧 Maintenance

### Monthly Scrub (Automatic)
- Runs: First Sunday of month at 2 AM
- Log: `/var/log/zfs-scrub.log`

### Manual Scrub
```bash
zpool scrub tank
watch -n 5 'zpool status tank'
```

## 📁 Dataset Structure

```
/tank/medien      → Media files (replaces /mnt/Medien)
/tank/config      → Docker configs
/tank/timemachine → Time Machine backups
/tank/backups     → System backups
```

## ⚠️ Important Notes

1. **Always use disk-by-id paths** (not /dev/sdX)
2. **Don't delete 2TB drive** until migration verified
3. **Resilver takes 2-3 hours** for 1TB of data
4. **Test Samba/Syncthing** after migration

## 🆘 Emergency Commands

### Pool won't import
```bash
zpool import -f tank
```

### Check for errors
```bash
zpool status -v tank
dmesg | grep -i zfs
```

### Destroy pool (DANGER!)
```bash
zpool destroy tank  # Only if rollback needed!
```

## 📖 Full Documentation

- Migration Guide: `~/code/pi/ZFS_MIGRATION_GUIDE.md`
- Role README: `~/code/pi/roles/zfs/README.md`
- Ansible Docs: `~/code/pi/AGENTS.md`
