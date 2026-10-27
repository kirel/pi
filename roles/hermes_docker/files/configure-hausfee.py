#!/usr/bin/env python3
"""Configure one Hausfee profile for every channel; preserve migration history."""
import copy
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import time

from ruamel.yaml import YAML

yaml = YAML()
yaml.preserve_quotes = True


def merge(base, overlay, delete_marker=None):
    for key, value in overlay.items():
        if delete_marker is not None and value == delete_marker:
            base.pop(key, None)
        elif isinstance(value, dict):
            base[key] = merge(base.get(key) if isinstance(base.get(key), dict) else {}, value, delete_marker)
        else:
            base[key] = copy.deepcopy(value)
    return base


def write_if_changed(path, text):
    if path.exists() and path.read_text() == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    owner = path.stat() if path.exists() else path.parent.stat()
    temporary = path.with_name(path.name + '.ansible-tmp')
    temporary.write_text(text)
    temporary.chmod(0o600)
    os.chown(temporary, owner.st_uid, owner.st_gid)
    temporary.replace(path)
    return True


def update_config(path, overlay, delete_marker=None):
    current = yaml.load(path.read_text()) if path.exists() else {}
    current = current if isinstance(current, dict) else {}
    updated = merge(copy.deepcopy(current), overlay, delete_marker)
    if current == updated:
        return False
    output = StringIO()
    yaml.dump(updated, output)
    return write_if_changed(path, output.getvalue())


def main():
    payload = json.load(sys.stdin)
    root = Path(os.environ.get('HERMES_HOME', '/opt/data'))
    profile = root / 'profiles' / 'hausfee'
    changed = False
    if profile.exists():
        archive = root / 'archives' / ('retired-hausfee-' + str(time.time_ns()))
        archive.parent.mkdir(parents=True, exist_ok=True)
        source_db = profile / 'state.db'
        target_db = root / 'state.db'
        if source_db.exists() and target_db.exists():
            # Import the brief conversation from the mistakenly created profile
            # so it remains searchable from the single retained profile. Do not
            # import routing: fresh turns must use the agreed identity and tools.
            with sqlite3.connect(target_db, timeout=30) as db:
                backup = archive.parent / 'state-before-hausfee-unification.db'
                if not backup.exists():
                    with sqlite3.connect(backup) as backup_db:
                        db.backup(backup_db)
                    backup.chmod(0o600)
                db.execute('ATTACH DATABASE ? AS retired', (str(source_db),))
                db.execute('BEGIN IMMEDIATE')
                fresh = [r[0] for r in db.execute(
                    'SELECT id FROM retired.sessions WHERE id NOT IN (SELECT id FROM main.sessions)')]
                if fresh:
                    columns = {}
                    for table in ('system_prompts', 'sessions', 'messages'):
                        dst = [r[1] for r in db.execute(f'PRAGMA main.table_info({table})')]
                        src = [r[1] for r in db.execute(f'PRAGMA retired.table_info({table})')]
                        if set(dst) != set(src):
                            raise RuntimeError('Refusing migration between different database schemas')
                        columns[table] = ','.join('"' + col + '"' for col in dst)
                    names = columns['system_prompts']
                    db.execute(f'INSERT OR IGNORE INTO main.system_prompts ({names}) SELECT {names} FROM retired.system_prompts')
                    marks = ','.join('?' for _ in fresh)
                    names = columns['sessions']
                    db.execute(f'INSERT INTO main.sessions ({names}) SELECT {names} FROM retired.sessions WHERE id IN ({marks})', fresh)
                    cols = [r[1] for r in db.execute('PRAGMA main.table_info(messages)') if r[1] != 'id']
                    names = ','.join('"' + col + '"' for col in cols)
                    db.execute(f'INSERT INTO main.messages ({names}) SELECT {names} FROM retired.messages WHERE session_id IN ({marks})', fresh)
                    db.execute(f"UPDATE main.sessions SET profile_name='default', ended_at=COALESCE(ended_at, ?), end_reason='profile-unification' WHERE id IN ({marks})", [time.time(), *fresh])
                db.commit()
            print('preserved_retired_sessions=' + str(len(fresh)))
        shutil.move(str(profile), str(archive))
        changed = True
    changed |= update_config(root / 'config.yaml', payload['transport_config'], payload['config_delete_marker'])
    changed |= update_config(root / 'profile.yaml', {'display_name': 'Hausfee'})
    soul = root / 'SOUL.md'
    soul_backup = root / 'archives' / 'SOUL-before-hausfee.md'
    if soul.exists() and not soul_backup.exists():
        soul_backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(soul, soul_backup)
    changed |= write_if_changed(soul, '# Hausfee\n\n' + payload['transport_config']['agent']['system_prompt'])
    # Login shells can replace the container PATH via /etc/profile. Restore the
    # persistent CLI installation after shell startup files have been sourced.
    changed |= write_if_changed(root / 'hausfee-shell.sh',
        'export PATH="/opt/data/npm-global/bin:/opt/data/.local/bin:$PATH"\n'
        'export NPM_CONFIG_PREFIX=/opt/data/npm-global\n'
        'export NPM_CONFIG_CACHE=/opt/data/home/.npm\n'
        'export NPM_CONFIG_USERCONFIG=/opt/data/home/.npmrc\n'
        'export GOOGLE_WORKSPACE_CLI_CONFIG_DIR=/opt/data/.config/gws\n')
    # Retain all secret and manually managed env entries verbatim.
    env_path = root / '.env'
    managed = payload['transport_env']
    lines = [line for line in env_path.read_text().splitlines()
             if line.partition('=')[0] not in managed]
    lines.extend(f'{key}={json.dumps(value)}' for key, value in sorted(managed.items()))
    changed |= write_if_changed(env_path, '\n'.join(lines) + '\n')
    print('changed' if changed else 'ok')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Ansible hides this task's output because it handles runtime credentials.
        # Keep only safe diagnostics, never the input/config/env, for recovery.
        diagnostic = {'type': type(exc).__name__}
        if isinstance(exc, (sqlite3.Error, RuntimeError)):
            diagnostic['reason'] = str(exc)
        Path('/tmp/hausfee-configure-error.json').write_text(json.dumps(diagnostic))
        raise
