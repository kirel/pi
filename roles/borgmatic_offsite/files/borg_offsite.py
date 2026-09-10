#!/usr/bin/python3
"""Prepare consistent backup inputs, then let borgmatic manage each repository."""
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import yaml

os.umask(0o077)
SETTINGS = json.loads(Path('/etc/borg-offsite.json').read_text())
LABEL = sys.argv[2]
if LABEL not in SETTINGS['profiles']:
    sys.exit('Unknown backup profile')
PROFILE = SETTINGS['profiles'][LABEL]
STAGE = Path(SETTINGS['stage']) / LABEL
VIEW = STAGE / 'view'
CONFIG = f'/etc/borgmatic.d/offsite-{LABEL}.yaml'
SNAPSHOT = f'borg-offsite-{LABEL}'
DATASETS = ('tank/immich/library', 'tank/medien')
STATUS = Path('/var/lib/borg-offsite/status') / f'{LABEL}.json'


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(stream):
    value = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        value.update(block)
    return value.digest()


def record(state, **values):
    data = json.loads(STATUS.read_text()) if STATUS.exists() else {}
    data.update(state=state, updated=timestamp(), **values)
    tmp = STATUS.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    tmp.replace(STATUS)


def borg_settings():
    config = yaml.safe_load(Path(CONFIG).read_text())
    env = os.environ.copy()
    env['BORG_PASSPHRASE'] = config['encryption_passphrase']
    env['BORG_RSH'] = config['ssh_command']
    return config['repositories'][0]['path'], env


def repo_init():
    repo, env = borg_settings()
    # Borg init refuses an existing repository: connection/auth failures cannot overwrite it.
    exists = subprocess.run(['borg', 'info', repo], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if not exists:
        run(['borg', 'init', '--encryption=repokey', repo], env=env)
    key = Path('/root/.config/borg/offsite-key-exports') / f'{LABEL}.key'
    if not key.exists():
        run(['borg', 'key', 'export', repo, str(key)], env=env)
        key.chmod(0o600)
    print('ok' if exists else 'created')


def resume_services():
    for marker in STAGE.glob('resume-service-*'):
        container = marker.name.removeprefix('resume-service-')
        run(['docker', 'start', container], stdout=subprocess.DEVNULL)
        marker.unlink()
    marker = STAGE / 'resume-immich'
    if marker.exists():
        run(['docker', 'start', 'immich_server'], stdout=subprocess.DEVNULL)
        marker.unlink()


def cleanup():
    resume_services()
    if VIEW.exists():
        mounts = json.loads(run(['findmnt', '--json', '--list', '-o', 'TARGET'],
                                capture_output=True, text=True).stdout)
        for target in sorted((m['target'] for m in mounts['filesystems']
                              if m['target'].startswith(str(VIEW) + '/')), key=len, reverse=True):
            run(['umount', target])
    for dataset in DATASETS:
        snap = f'{dataset}@{SNAPSHOT}'
        if subprocess.run(['zfs', 'list', '-H', '-t', 'snapshot', snap],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            run(['zfs', 'destroy', snap])


def bind(source, relative):
    target = VIEW / relative
    target.mkdir(parents=True, exist_ok=True)
    run(['mount', '--bind', str(source), str(target)])
    run(['mount', '-o', 'remount,bind,ro', str(target)])


def dump_postgres(container, destination):
    tmp = destination.with_suffix('.tmp')
    with tmp.open('wb') as output:
        run(['docker', 'exec', container, 'sh', '-c',
             'exec pg_dumpall -U "$POSTGRES_USER"'], stdout=output)
    if tmp.stat().st_size == 0:
        raise RuntimeError(f'Empty database dump from {container}')
    tmp.replace(destination)


def prepare():
    cleanup()
    print('Staging application configuration', flush=True)
    STAGE.mkdir(parents=True, exist_ok=True)
    config_copy = STAGE / 'config'
    config_copy.mkdir(exist_ok=True)
    dumps = STAGE / 'database-dumps'
    dumps.mkdir(exist_ok=True)
    source = Path(SETTINGS['config_source'])
    args = ['rsync', '-a', '--delete']
    for pattern in SETTINGS['excludes']:
        args += ['--exclude', pattern]
    run(args + [str(source) + '/', str(config_copy) + '/'])
    # Some applications hold SQLite exclusive locks for their entire lifetime.
    # Copy just those small directories after a clean stop, then resume promptly.
    for directory, container in SETTINGS.get('paused_sources', {}).items():
        running = run(['docker', 'inspect', '-f', '{{.State.Running}}', container],
                      capture_output=True, text=True).stdout.strip() == 'true'
        try:
            if running:
                (STAGE / f'resume-service-{container}').touch()
                run(['docker', 'stop', '-t', '60', container], stdout=subprocess.DEVNULL)
            run(['rsync', '-a', '--delete', '--ignore-times', str(source / directory) + '/',
                 str(config_copy / directory) + '/'])
        finally:
            resume_services()
    print('Preparing online SQLite backups and PostgreSQL dumps', flush=True)
    # Replace copied SQLite files with online backups, so live WAL writes cannot
    # produce an internally inconsistent database. Preserve relative restore paths.
    count = 0
    for path in config_copy.rglob('*'):
        if path.relative_to(config_copy).parts[0] in SETTINGS.get('paused_sources', {}):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix not in ('.db', '.sqlite', '.sqlite3'):
            continue
        with path.open('rb') as f:
            if f.read(16) != b'SQLite format 3\x00':
                continue
        original = source / path.relative_to(config_copy)
        tmp = path.with_name(path.name + '.offsite-tmp')
        deadline = time.monotonic() + 1800
        def progress(status, remaining, total):
            if time.monotonic() > deadline:
                raise TimeoutError(f'SQLite backup timed out: {original}')
        with contextlib.closing(sqlite3.connect(original.as_uri() + '?mode=ro', uri=True)) as src:
            # Pin a read snapshot so continuous WAL writers cannot restart each
            # incremental backup step. WAL-mode application writes can continue.
            src.execute('BEGIN')
            src.execute('SELECT name FROM sqlite_master LIMIT 1').fetchone()
            with contextlib.closing(sqlite3.connect(tmp)) as dst:
                src.backup(dst, pages=1024, progress=progress)
        shutil.copystat(original, tmp)
        stat = original.stat()
        os.chown(tmp, stat.st_uid, stat.st_gid)
        tmp.replace(path)
        for suffix in ('-wal', '-shm', '-journal'):
            Path(str(path) + suffix).unlink(missing_ok=True)
        count += 1
    for container in SETTINGS['postgres']:
        if container != 'immich_postgres':
            dump_postgres(container, dumps / f'{container}.sql')
    # Briefly pause Immich writes while capturing its database and asset snapshots.
    running = run(['docker', 'inspect', '-f', '{{.State.Running}}', 'immich_server'],
                  capture_output=True, text=True).stdout.strip() == 'true'
    try:
        if running:
            (STAGE / 'resume-immich').touch()
            run(['docker', 'stop', '-t', '60', 'immich_server'], stdout=subprocess.DEVNULL)
        dump_postgres('immich_postgres', dumps / 'immich_postgres.sql')
        run(['zfs', 'snapshot'] + [f'{d}@{SNAPSHOT}' for d in DATASETS])
    finally:
        resume_services()
    bind(config_copy, 'home/nuc/config')
    bind(dumps, 'database-dumps')
    bind(f'/tank/immich/library/.zfs/snapshot/{SNAPSHOT}', 'tank/immich/library')
    for directory in PROFILE['media']:
        bind(f'/tank/medien/.zfs/snapshot/{SNAPSHOT}/{directory}', f'tank/medien/{directory}')
    (dumps / 'backup-metadata.json').write_text(json.dumps({
        'prepared': timestamp(), 'sqlite_online_backups': count,
        'postgres_containers': SETTINGS['postgres'], 'media': PROFILE['media'],
        'paused_sources': SETTINGS.get('paused_sources', {}),
        'snapshot': SNAPSHOT,
    }, indent=2))
    print(f'Prepared {count} SQLite backups, PostgreSQL dumps and ZFS snapshots', flush=True)


def backup():
    with open('/run/lock/borg-offsite.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        record('running', started=timestamp())
        try:
            repo, env = borg_settings()
            run(['borg', 'info', repo], env=env, stdout=subprocess.DEVNULL)
            prepare()
            run(['borgmatic', '--config', CONFIG, 'create', '--stats'])
            record('verifying', last_backup=timestamp())
            verify_latest()
            record('checking', last_backup=timestamp())
            run(['borgmatic', '--config', CONFIG, 'prune', 'compact', 'check'])
            record('success', last_success=timestamp())
        except Exception:
            record('failed', failed=timestamp())
            raise
        finally:
            cleanup()


def verify_latest():
    """Restore selected real files into a hash stream without exposing their contents."""
    repo, env = borg_settings()
    archives = json.loads(run(['borg', 'list', '--json', '--last', '1',
        '--glob-archives', f'homelab-offsite-{LABEL}-*', repo], env=env,
        capture_output=True, text=True).stdout)['archives']
    if not archives:
        raise RuntimeError('No completed archive to verify')
    archive = repo + '::' + archives[0]['name']
    files = [VIEW / 'database-dumps/backup-metadata.json']
    files += [VIEW / 'database-dumps' / f'{c}.sql' for c in SETTINGS['postgres']]
    for path in (VIEW / 'home/nuc/config').rglob('*'):
        if path.is_file() and not path.is_symlink() and path.suffix in ('.db', '.sqlite', '.sqlite3'):
            with path.open('rb') as stream:
                if stream.read(16) == b'SQLite format 3\x00':
                    files.append(path)
                    break
    for path in (VIEW / 'tank/immich/library').rglob('*'):
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in ('.jpg', '.jpeg', '.heic', '.png'):
            files.append(path)
            break
    for path in files:
        with path.open('rb') as stream:
            expected = digest(stream)
        with subprocess.Popen(['borg', 'extract', '--stdout', archive,
                               str(path.relative_to(VIEW))], env=env,
                              stdout=subprocess.PIPE) as process:
            restored = digest(process.stdout)
            if process.wait() != 0 or restored != expected:
                raise RuntimeError('Real-file restore verification failed')
    print(f'{LABEL}: restored {len(files)} real backup files; SHA-256 matches', flush=True)


def smoke():
    repo, env = borg_settings()
    directory = Path('/var/lib/borg-offsite/verification')
    directory.mkdir(exist_ok=True)
    path = directory / f'{LABEL}.txt'
    payload = ('Borg offsite round-trip ' + timestamp()).encode()
    path.write_bytes(payload)
    archive = 'verification-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')
    run(['borg', 'create', repo + '::' + archive, path.name], cwd=directory, env=env)
    restored = run(['borg', 'extract', '--stdout', repo + '::' + archive, path.name],
                   env=env, capture_output=True).stdout
    if restored != payload:
        raise RuntimeError('Restore verification mismatch')
    run(['borg', 'check', '--repository-only', repo], env=env)
    run(['borg', 'delete', repo + '::' + archive], env=env)
    path.unlink()
    print(f'{LABEL}: encrypted archive, repository check and restore verified')


if __name__ == '__main__':
    {'init': repo_init, 'run': backup, 'cleanup': cleanup, 'smoke': smoke,
     'verify': verify_latest}[sys.argv[1]]()
