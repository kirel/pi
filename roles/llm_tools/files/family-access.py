#!/usr/bin/env python3
"""Reconcile SSO subjects and existing bot-key ownership without rotating keys."""
import json
import sys
import urllib.parse
import urllib.request

payload = json.load(sys.stdin)
base = payload['base_url'].rstrip('/')


def api(method, path, data=None):
    req = urllib.request.Request(
        base + path, method=method,
        data=json.dumps(data).encode() if data is not None else None,
        headers={'Authorization': 'Bearer ' + payload['master_key'],
                 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        body = response.read()
        return json.loads(body) if body else None


try:
    changed = False
    if sys.argv[1] == 'users':
        result = api('GET', '/user/list?page_size=100')
        users = result if isinstance(result, list) else result['users']
        for username, desired in payload['users'].items():
            role = desired.get('user_role', 'internal_user_viewer')
            assert role in ('internal_user_viewer', 'proxy_admin_viewer'), 'Expected a read-only user role'
            matches = [u for u in users if u['user_id'] == desired['id']]
            if matches:
                assert (matches[0].get('user_email') or '').lower() == desired['email'].lower(), 'User email mismatch'
                if 'user_role' in desired and matches[0].get('user_role') != role:
                    api('POST', '/user/update', {'user_id': desired['id'], 'user_role': role})
                    changed = True
                continue
            assert not any((u.get('user_email') or '').lower() == desired['email'].lower() for u in users), 'Existing email has another subject'
            api('POST', '/user/new', {
                'user_id': desired['id'], 'user_email': desired['email'],
                'user_role': role, 'auto_create_key': False,
                'send_invite_email': False})
            changed = True
    elif sys.argv[1] == 'bindings':
        for alias, desired in payload['bindings'].items():
            result = api('GET', '/key/list?return_full_object=true&size=100&key_alias=' + urllib.parse.quote(alias))
            matches = [k for k in result['keys'] if k.get('key_alias') == alias]
            assert len(matches) == 1, 'Expected exactly one existing key'
            key = matches[0]
            permissions = dict(key.get('object_permission') or {})
            permissions.pop('object_permission_id', None)
            groups = list(permissions.get('mcp_access_groups') or [])
            subject = payload['users'][desired['username']]['id']
            if key.get('user_id') == subject and key.get('team_id') == desired['team_id'] and 'craft_family' in groups:
                continue
            if 'craft_family' not in groups:
                groups.append('craft_family')
            permissions['mcp_access_groups'] = groups
            api('POST', '/key/update', {
                'key': key['token'], 'user_id': subject,
                'team_id': desired['team_id'], 'object_permission': permissions})
            changed = True
    else:
        raise ValueError('Unknown reconciliation phase')
    print('FAMILY_CHANGED' if changed else 'FAMILY_OK')
except Exception as error:
    print('Family access reconciliation failed: ' + type(error).__name__, file=sys.stderr)
    sys.exit(1)
