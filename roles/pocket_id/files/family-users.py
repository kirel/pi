#!/usr/bin/env python3
"""Create declared identities; preserve existing accounts, passkeys and groups."""
import json
from pathlib import Path
import sys
import urllib.request

root, base = sys.argv[1:]
key = (Path(root) / 'secrets/automation-key').read_text().strip()
desired = json.load(sys.stdin)


def api(method, path, data=None):
    req = urllib.request.Request(
        base + '/api' + path, method=method,
        data=json.dumps(data).encode() if data is not None else None,
        headers={'X-API-KEY': key, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=20) as response:
        body = response.read()
        return json.loads(body) if body else None


try:
    changed = False
    users = api('GET', '/users?limit=100')['data']
    for username, fields in desired.items():
        matches = [u for u in users if u['username'] == username or u['id'] == fields['id']]
        if not matches:
            user = api('POST', '/users', dict(fields, username=username, isAdmin=False))
            assert user['id'] == fields['id'], 'Unexpected Pocket ID subject'
            users.append(user)
            changed = True
        else:
            assert len(matches) == 1 and matches[0]['id'] == fields['id'], 'Identity mismatch'
            assert (matches[0].get('email') or '').lower() == fields['email'].lower(), 'Email mismatch'
    if desired:
        groups = api('GET', '/user-groups?limit=100')['data']
        group = next((g for g in groups if g['name'] == 'family'), None)
        if group is None:
            group = api('POST', '/user-groups', {'name': 'family', 'friendlyName': 'Family'})
            changed = True
        detail = api('GET', '/user-groups/' + group['id'])
        current = {u['id'] for u in detail.get('users', [])}
        members = current | {u['id'] for u in desired.values()}
        if current != members:
            api('PUT', '/user-groups/' + group['id'] + '/users', {'userIds': sorted(members)})
            changed = True
    print('FAMILY_CHANGED' if changed else 'FAMILY_OK')
except Exception as error:
    print('Family identity reconciliation failed: ' + type(error).__name__, file=sys.stderr)
    sys.exit(1)
