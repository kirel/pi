#!/usr/bin/python3
"""Remove only the unused legacy pool; preserve the underlying filesystems."""
import json
import pathlib
import pwd
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET


def read(model):
    return json.loads(subprocess.check_output(['omv-confdbadm', 'read', model]))


def rpc(service, method, params):
    subprocess.run(['omv-rpc', '-u', 'admin', service, method, json.dumps(params)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    user = sys.argv[1]
    changed = False
    pools = read('conf.service.mergerfs.pool')
    for pool in pools:
        if pool['name'] != 'backup_pool':
            continue
        shares = [s for s in read('conf.system.sharedfolder') if s['mntentref'] == pool['mntentref']]
        tree = ET.parse('/etc/openmediavault/config.xml')
        for share in shares:
            if any(e.text == share['uuid'] and e.tag != 'uuid' for e in tree.iter()):
                raise RuntimeError('Legacy pool shared folder still has consumers')
        # Refuse an unexpected populated pool. Never remove filesystem contents.
        root = pathlib.Path('/srv/mergerfs/backup_pool')
        if root.is_mount():
            allowed = {'aquota.user', 'aquota.group', 'lost+found', 'backups'}
            if any(p.name not in allowed for p in root.iterdir()):
                raise RuntimeError('Legacy pool contains unexpected data')
            if (root / 'backups').exists() and any((root / 'backups').iterdir()):
                raise RuntimeError('Legacy backup directory is not empty')
        backup = pathlib.Path('/root/omv-before-separate-borg-disks.xml')
        if not backup.exists():
            shutil.copyfile('/etc/openmediavault/config.xml', backup)
            backup.chmod(0o600)
        for share in shares:
            rpc('ShareMgmt', 'delete', {'uuid': share['uuid'], 'recursive': False})
        subprocess.run(['systemctl', 'stop', 'srv-mergerfs-backup_pool.mount'], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        rpc('Mergerfs', 'delete', {'uuid': pool['uuid']})
        subprocess.run(['omv-salt', 'deploy', 'run', 'mergerfs', 'fstab'], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        changed = True
    users = read('conf.system.usermngmnt.user')
    if not any(u['name'] == user for u in users):
        try:
            pwd.getpwnam(user)
        except KeyError:
            pass
        else:
            raise RuntimeError('Existing unmanaged backup user needs review')
        rpc('UserMgmt', 'setUser', dict(name=user, groups=['_ssh'], shell='/bin/sh',
            password='', email='', comment='Restricted Borg offsite repository access',
            disallowusermod=True, sshpubkeys=[]))
        changed = True
    print('changed' if changed else 'ok')


if __name__ == '__main__':
    main()
