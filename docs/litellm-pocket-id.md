# LiteLLM Pocket ID login

The first stage adds native OIDC browser login to LiteLLM. Pocket ID currently
allows only its `admins` group to use `litellm-pocket-id`. This does not grant
LiteLLM administrator privileges: new accounts without an assigned role default
to `internal_user_viewer` (the installed version's INTERNAL_USER_VIEW_ONLY role).
The stable identity is Pocket ID's `sub`; existing keys are not reassigned.

- UI: https://litellm.kirelabs.org/ui
- Existing password/admin login: https://litellm.kirelabs.org/fallback/login
- OIDC callback: https://litellm.kirelabs.org/sso/callback
- Client registry: `group_vars/all/pocket_id.yml`
- OIDC environment: `roles/llm_tools/tasks/main.yml`

The existing Pocket ID reconciler generates the client secret into its protected
host-local secrets directory. Ansible consumes it with `no_log` and `diff: false`.
No upstream MCP OAuth connections or Hermes settings are changed in this stage.

Deploy the client before deploying LiteLLM:

```sh
uv run ansible-playbook setup.yml --tags pocket-id --limit homelab
uv run ansible-playbook setup.yml --tags llm-tools --limit homelab \
  -e '{"llm_tools_compose_services":["litellm-proxy"],"litellm_managed_virtual_keys":{}}'
```

The second command limits Compose to the proxy and skips managed-key sync.
Wait for `/health/readiness` after deployment. Confirm SSO uses S256 PKCE and the
public callback, and that `/fallback/login` still accepts the existing login.
Complete a real Pocket ID passkey login before considering browser onboarding
validated. Check the resulting account role and absence of unintended access.

Rollback: remove the LiteLLM `GENERIC_*` environment additions and its secret-read
task, then redeploy the proxy with the command above. The unused Pocket ID client
can remain for a later retry; retain existing identity and application data.

LiteLLM documents free SSO for up to five users; check licensing and the installed
version's billable-user count before expanding access.

References: https://docs.litellm.ai/docs/proxy/admin_ui_sso

Validation on 2026-09-08: syntax and diff checks passed; scoped deployment
completed without failures. Public readiness returned 200. SSO returned 303 to
Pocket ID with the expected callback and S256 PKCE. A deliberately invalid code
returned `invalid_grant` after client authentication. Existing admin login returned
303 with a session cookie; models returned 200 with authentication and 401 without.
The personal passkey login and resulting account permissions remain to be tested
by Daniel. No upstream OAuth migration has been performed.
