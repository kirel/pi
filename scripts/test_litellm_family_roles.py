"""Run with python3 scripts/test_litellm_family_roles.py."""
import contextlib
import io
import json
from pathlib import Path
import runpy
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'roles/llm_tools/files/family-access.py'


def check(existing_role, desired_role, expected_writes):
    desired = {'id': 'test-user', 'email': 'test@example.invalid'}
    if desired_role is not None:
        desired['user_role'] = desired_role
    users = [] if existing_role is None else [{
        'user_id': desired['id'], 'user_email': desired['email'],
        'user_role': existing_role}]
    writes = []

    def respond(request, timeout):
        if request.method == 'GET':
            return io.BytesIO(json.dumps({'users': users}).encode())
        writes.append((request.full_url.rsplit('/', 1)[-1], json.loads(request.data)))
        return io.BytesIO(b'{}')

    payload = {'base_url': 'https://test.invalid', 'master_key': 'test-only',
               'users': {'test': desired}}
    with patch('sys.stdin', io.StringIO(json.dumps(payload))), \
         patch('sys.argv', [str(SCRIPT), 'users']), \
         patch('urllib.request.urlopen', respond), contextlib.redirect_stdout(io.StringIO()):
        runpy.run_path(str(SCRIPT), run_name='__main__')
    assert writes == expected_writes, writes


check('internal_user_viewer', 'proxy_admin_viewer', [
    ('update', {'user_id': 'test-user', 'user_role': 'proxy_admin_viewer'})])
check('proxy_admin_viewer', 'proxy_admin_viewer', [])
check('proxy_admin_viewer', None, [])
check(None, 'proxy_admin_viewer', [('new', {
    'user_id': 'test-user', 'user_email': 'test@example.invalid',
    'user_role': 'proxy_admin_viewer', 'auto_create_key': False, 'send_invite_email': False})])
print('LiteLLM role reconciliation checks passed')
