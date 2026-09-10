# Pocket ID

Pocket ID at <https://id.kirelabs.org> is the identity provider for the following
13 applications. Daniel's existing passkey and `admins` membership are reused.
The Linkding pilot was accepted by Daniel; other applications still require a
real browser login to confirm account linking and the desired user experience.

## Deployed integrations

| Application | Integration | Notes |
| --- | --- | --- |
| [Linkding](https://linkding.kirelabs.org) | Native OIDC | Existing admin and bookmarks retained; user-tested |
| [Beszel](https://beszel.kirelabs.org) | Native OIDC | Existing user and agent credentials preserved; PKCE |
| [Readeck](https://readeck.kirelabs.org) | Native OIDC | Pocket ID button on login form |
| [TeslaMate Grafana](https://teslamate-grafana.kirelabs.org) | Native OIDC | `admins` maps to organization Admin, anonymous access disabled |
| [Open WebUI](https://open-webui.kirelabs.org) | Native OIDC | Existing accounts linked by verified email; local login retained |
| [Immich](https://immich.kirelabs.org) | Native OIDC | Web and mobile callbacks; no automatic new account creation |
| [Dockhand](https://dockhand.kirelabs.org) | Native OIDC | Authentication enabled, Pocket ID default; local recovery account |
| [Homepage](https://homepage.kirelabs.org) | OAuth2 Proxy | Former Authelia Forward Auth |
| [PruneMate](https://prunemate.kirelabs.org) | OAuth2 Proxy | Former Authelia Forward Auth |
| [DHCP leases, NUC](https://leases-homelab.kirelabs.org) | OAuth2 Proxy | Former Authelia Forward Auth |
| [Dozzle](https://dozzle.kirelabs.org) | OAuth2 Proxy + trusted headers | Dozzle itself has no native OIDC in this integration |
| [ChangeDetection](https://changedetection.kirelabs.org) | OAuth2 Proxy | `/api/v1/` retains native API-key authentication |
| [TeslaMate](https://teslamate.kirelabs.org) | OAuth2 Proxy | Vehicle ingestion is independent of browser login |

Every client currently requires `admins`. Application roles and authorization
remain separate from permission to start an OIDC login. In particular, granting
access to a client does not automatically grant an application's administrator
role, except where explicitly configured (Grafana and Dockhand).

Pocket ID remains LAN/Tailnet-only. Public applications such as Immich can still
use their existing password/API access externally; Pocket ID login currently
requires access to the LAN or VPN, including from a mobile browser.

## Configuration ownership

- `group_vars/all/pocket_id.yml`: native OIDC clients, exact callbacks and PKCE.
- `group_vars/all/services.yml`: proxy clients, groups and local proxy ports.
  The Pocket ID role derives these clients from the registry.
- Pocket ID UI: users, passkeys and membership in groups. Ansible does not reset
  user memberships during reconciliation.
- Application roles: OIDC consumer settings and application-specific permissions.
- `roles/pocket_id_proxy`: OAuth2 Proxy v7.15.4, one instance and independent
  host-only secure cookie per application. No cookie shared across subdomains.

Native client definitions optionally accept `groups`; the default is `admins`.
Proxy group changes require redeploying both `pocket-id` and `pocket-id-proxy`.
Removing a registry entry does not automatically delete old IdP clients/secrets.
Retire unused clients explicitly after checking for consumers.

The six proxy-protected backends publish only on loopback. The proxy containers
also listen only on loopback, run as UID 65532 with dropped capabilities, and use
read-only secret files. Caddy removes incoming identity headers before proxying.
The ChangeDetection API exception relies on the backend's API-key enforcement;
an anonymous request was verified to return 403. Do not add API exceptions unless
the backend independently authenticates those requests.

## Secrets and recovery

Persistent keys are created on the NUC under `/home/nuc/config/pocket-id/secrets`.
They are not in Git and are not automatically copied to 1Password. No auth
backups were created, as requested. Rebuilding from Git alone will not recover
the Pocket ID identity database or keys.

- The automation key is a full administrator credential exclusively for Ansible.
- Each client has its own secret. Reconciliation retains existing IDs/secrets.
- `dockhand-recovery-password` belongs to the local `ansible-recovery` account;
  it is consumed locally by the reconciliation script and is never logged.
- Open WebUI now uses `open-webui-session-key` instead of its old fixed placeholder.
  This invalidates old WebUI sessions once.
- Daniel's existing email was marked verified during migration. Only administrators
  should assign verified emails; email matching can link existing app accounts.

Keep at least two independent passkeys. Local application password fallbacks
remain enabled pending individual browser acceptance. Immich existing users can
link OAuth from user settings; automatic creation is disabled to avoid duplicate
photo accounts. Grafana may create a distinct OIDC user; the old local admin
remains available and dashboards are organization-owned.

An OIDC logout/group removal is not guaranteed to terminate all application
sessions immediately. Auth-proxy cookies last one hour and refresh after five
minutes; verify revocation latency before depending on it for emergency access
removal. API tokens retain their independent lifecycle.

## Deployment

```bash
uv run ansible-playbook setup.yml --tags pocket-id --limit homelab
uv run ansible-playbook setup.yml --tags pocket-id-proxy,caddy --limit homelab
uv run ansible-playbook setup.yml --tags pihole --limit nameserver,homelab
uv run ansible-playbook setup.yml --tags beszel,readeck,teslamate --limit homelab
uv run ansible-playbook pocket-id-apps.yml --limit homelab
```

To update only Open WebUI within the LiteLLM Compose project:

```bash
uv run ansible-playbook setup.yml --tags llm-tools --limit homelab \
  -e '{"llm_tools_compose_services":["open-webui"]}'
```

The API-only playbook reconciles Immich and Dockhand without redeploying their
stacks. Their normal roles also include that reconciliation.

## Verification and remaining coverage

Verified: client credentials accepted for all 13 clients; all client group
restrictions read back as `admins`; application OIDC endpoints/login buttons;
all six proxies reject anonymous auth and forged identity headers; all six
backend bindings read back as loopback-only. Browser callbacks, account linking,
mobile login, role mapping, logout and group revocation still need individual
acceptance beyond the already accepted Linkding pilot.

The following services were not put behind blanket browser SSO:

| Services | Reason / remaining work |
| --- | --- |
| Jellyfin | Pocket ID's example uses an archived plugin and documents mobile/TV limitations; evaluate a maintained integration first |
| Home Assistant, Hermes Assist, Music Assistant | App/device authentication and callbacks; no verified native OIDC integration in this rollout |
| Node-RED, Portainer | Retired; no migration planned |
| LiteLLM, CPA, CPA Usage, Phoenix, Google Workspace MCP | API/MCP consumers; assess UI-only authentication separately |
| ComfyUI, Wan2GP, LlamaSwap | Cross-host inference/MCP/file workflows; require backend allowlists and explicit machine paths before a proxy rollout |
| T3 Code and Hermes dashboards/WebUIs | Cross-host browser/WebSocket and agent publishing paths need separate validation |
| qBittorrent, Prowlarr, Sonarr, Radarr, Seerr | Automation/download/native-token flows; inventory API/indexer exceptions before adding a proxy |
| Uptime Kuma | Push endpoints and AutoKuma clients; retain native auth until route exceptions are validated |
| Pi-hole UIs, nameserver DHCP leases, Syncthing UIs | Cross-host admin APIs; need backend policy and caller verification |
| Zigbee2MQTT, evcc, TeddyCloud, Navidrome | Device/API/media clients; blanket login redirects would need client-specific tests |
| Brumm | Existing shared external access; user/group migration is a separate decision |

Authelia, Node-RED and Portainer are retired. Their runtime containers and
active deployment/service definitions have been removed. Existing persistent
data is retained, but these services are not automatically restored by Ansible.
The historical encrypted `authelia_secrets.yml` is retained because it also
contains the active Beszel bootstrap credential. Jellyfin remains unchanged.

References: [Pocket ID client examples](https://pocket-id.org/docs/client-examples),
[proxy integrations](https://pocket-id.org/docs/guides/proxy-services),
[OAuth2 Proxy options](https://oauth2-proxy.github.io/oauth2-proxy/configuration/overview/).
