#!/usr/bin/env python3
"""Manage Dockhand's native OIDC provider without exposing credentials."""
import http.cookiejar
import json
import os
import pathlib
import secrets
import sys
import urllib.request

root = pathlib.Path(sys.argv[1])
base = sys.argv[2]
issuer = sys.argv[3]
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def api(path, method='GET', body=None):
    req = urllib.request.Request(base + '/api' + path, method=method,
        headers={'Content-Type': 'application/json', 'Origin': base},
        data=json.dumps(body).encode() if body is not None else None)
    with opener.open(req, timeout=20) as response:
        return json.load(response)


try:
    password_file = root / 'secrets/dockhand-recovery-password'
    if not password_file.exists():
        fd = os.open(password_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(secrets.token_urlsafe(36))
    password = password_file.read_text()
    # Public endpoint remains available after authentication is enabled.
    enabled = bool(api('/auth/providers')['providers'])
    if enabled:
        api('/auth/login', 'POST', {'username': 'ansible-recovery', 'password': password})
    else:
        users = api('/users')
        if not any(u['username'] == 'ansible-recovery' for u in users):
            api('/users', 'POST', {'username': 'ansible-recovery', 'password': password,
                                 'displayName': 'Local recovery (Ansible)'})
    providers = api('/auth/oidc')
    provider = next((p for p in providers if p['clientId'] == 'dockhand-pocket-id'), None)
    desired = dict(name='Pocket ID', enabled=True, issuerUrl=issuer,
                   clientId='dockhand-pocket-id', redirectUri=base + '/api/auth/oidc/callback',
                   scopes='openid profile email groups', usernameClaim='preferred_username',
                   emailClaim='email', displayNameClaim='name', adminClaim='groups', adminValue='admins')
    changed = False
    if provider is None or any(provider.get(k) != v for k, v in desired.items()):
        desired['clientSecret'] = (root / 'secrets/dockhand-client-secret').read_text()
        provider = api('/auth/oidc' + ('/' + str(provider['id']) if provider else ''),
                       'PUT' if provider else 'POST', desired)
        changed = True
    if not enabled:
        api('/auth/settings', 'PUT', {'authEnabled': True, 'defaultProvider': 'oidc:' + str(provider['id'])})
        changed = True
        api('/auth/login', 'POST', {'username': 'ansible-recovery', 'password': password})
    assert any(p.get('name') == 'Pocket ID' for p in api('/auth/providers')['providers'])
    api('/auth/logout', 'POST', {})
    print('OIDC_CHANGED' if changed else 'OIDC_OK')
except Exception as error:
    print('Dockhand reconciliation failed: ' + type(error).__name__, file=sys.stderr)
    sys.exit(1)
