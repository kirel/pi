#!/usr/bin/env python3
"""Run on Ailab: hand off CLI and one explicit secret directly over SSH stdin."""
import json
from pathlib import Path
import shlex
import subprocess
import sys

config = json.load(sys.stdin)


def transfer(data, destination, mode):
    receiver = f'''
import os, sys
from pathlib import Path
path = Path({destination!r})
path.parent.mkdir(parents=True, exist_ok=True)
data = sys.stdin.buffer.read()
assert data, 'Empty handover'
changed = not path.exists() or path.read_bytes() != data
if changed:
    temporary = path.with_name(path.name + '.ansible-tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, {mode})
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
    temporary.chmod({mode})
    temporary.replace(path)
if path.stat().st_mode & 0o777 != {mode}:
    path.chmod({mode})
    changed = True
print('changed' if changed else 'ok')
'''
    remote = shlex.join(['docker', 'exec', '-i', '--user', 'hermes',
                         'hermes-multipurpose', '/opt/hermes/.venv/bin/python',
                         '-c', receiver])
    result = subprocess.run(
        ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
         config['target'], remote], input=data, capture_output=True, timeout=90)
    if result.returncode:
        raise RuntimeError('SSH handover failed')
    return result.stdout.strip() == b'changed'


try:
    version = subprocess.check_output(['/usr/bin/op', '--version'], text=True).strip()
    assert version == config['version'], 'Source CLI version differs from declared version'
    changed = transfer(Path('/usr/bin/op').read_bytes(),
                       '/opt/data/.local/lib/1password/op', 0o755)
    result = subprocess.run(
        ['/usr/local/bin/op-sa', 'read', '--no-newline', config['reference']],
        capture_output=True, timeout=45)
    if result.returncode or not result.stdout:
        raise RuntimeError('1Password handover read failed')
    changed |= transfer(result.stdout, '/opt/data/.config/op/service-account-token', 0o600)
    print('changed' if changed else 'ok')
except Exception as error:
    print('1Password provisioning failed: ' + type(error).__name__, file=sys.stderr)
    sys.exit(1)
