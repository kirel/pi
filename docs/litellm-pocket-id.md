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

## Daniel's Craft pilot

Daniel confirmed the Pocket ID browser login. His SSO identity is
`fa559a90-e4e0-4793-8aaa-594bce6fbe06` (`internal_user_viewer`).

The central `craft` MCP entry uses `https://mcp.craft.do/my/mcp` with
`oauth2` / `authorization_code`, scoped to `craft_personal_pilot`.
A separate `hermes-daniel-personal-pilot` team is declared in
`group_vars/all/hermes_mcp.yml`. Its personally owned runtime key has the same
alias, preserves the previous Hermes model/MCP scope and Todoist tool allowlist,
and adds Craft. The previous `hermes` key and team have not gained Craft access.

The new key is stored only in 1Password and LiteLLM's credential database:
`op://homelab/6zduarevk6sf7s2bidaecujcne/credential`
(item title: `LiteLLM Daniel personal Hermes pilot`). This pilot key is not part
of the existing Ansible Vault backed key reconciler; do not regenerate or rotate
it during ordinary deployments. Its team permissions are declarative.

Client endpoint: `https://litellm.kirelabs.org/mcp/`. Use
`x-litellm-api-key: Bearer <key>` for gateway admission. Daniel will configure
his bare-metal Hermes separately. The existing direct Craft connection remains.

Validation: the stored key authenticates `/v1/models`, can list the Craft server,
and has the expected personal user ID. Upstream credential status is currently
not connected. Dynamic registration through LiteLLM succeeded (200), followed
by a Craft authorization redirect (307). Daniel must connect Craft through his
personal LiteLLM UI before end-to-end tool calls and token refresh can be tested.
The initial authorize probe without DCR returned `missing_client_id`; the normal
registration followed by authorization succeeded.
