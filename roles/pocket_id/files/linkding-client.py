#!/usr/bin/env python3
"""Reconcile the pilot client; secrets never leave the service host or stdout."""
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

root = pathlib.Path(sys.argv[1])
base = sys.argv[2]
manifest = json.loads(pathlib.Path(sys.argv[3]).read_text())
key = (root / 'secrets/automation-key').read_text().strip()
changed = False


def api(method, path, data=None):
    request = urllib.request.Request(
        base + '/api' + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={'X-API-KEY': key, 'Content-Type': 'application/json'},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read()
        return json.loads(body) if body else None


try:
    groups = api('GET', '/user-groups?limit=100')['data']
    for name, config in manifest.items():
        allowed = []
        for group_name in config.get('groups', ['admins']):
            entry = next((g for g in groups if g['name'] == group_name), None)
            if entry is None:
                entry = api('POST', '/user-groups', {'name': group_name, 'friendlyName': group_name})
                groups.append(entry)
                changed = True
            allowed.append(entry['id'])
        path = '/oidc/clients/' + config.get('client_id', name + '-pocket-id')
        desired = {'name': config['name'], 'callbackURLs': config['callbacks'],
               'logoutCallbackURLs': [], 'isPublic': False,
               'pkceEnabled': config.get('pkce', False), 'isGroupRestricted': True,
               'launchURL': config['url']}
        try:
            client = api('GET', path)
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            api('POST', '/oidc/clients', dict(desired, id=path.rsplit('/', 1)[1]))
            client = api('GET', path)
            changed = True
        if any(client.get(k) != v for k, v in desired.items()):
            api('PUT', path, desired)
            changed = True
        if {g['id'] for g in client.get('allowedUserGroups', [])} != set(allowed):
            api('PUT', path + '/allowed-user-groups', {'userGroupIds': allowed})
            changed = True
        secret_path = root / ('secrets/' + name + '-client-secret')
        if not secret_path.exists():
            secret = api('POST', path + '/secrets', {})['secret']
            fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as stream:
                stream.write(secret)
            changed = True
    print('CLIENT_CHANGED' if changed else 'CLIENT_OK')
except Exception as error:
    # Avoid response bodies, request headers and credentials in Ansible logs.
    print('Client reconciliation failed: ' + type(error).__name__, file=sys.stderr)
    sys.exit(1)
