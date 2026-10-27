# Temporary LiteLLM on Dashserv

Parallel restore for the house move. All six Hetzner Hermes runtimes now use the remote endpoint. The NUC was shut
down at Daniel's explicit request after the cutover for a real outage test. The remote instance is an independent snapshot,
not a replica: key changes, spend/budget counters and new logs do not synchronize.

## Locations

- Endpoint: `https://litellm-remote.kirelabs.org`, Tailnet only.
- Host: `dashserv-m-1`, public SSH `77.90.42.61`, Tailnet `100.121.44.75`.
- Runtime: `/opt/litellm-remote` (root-only, includes credentials).
- Backup on source and destination: `/var/backups/litellm-remote-20261021`.
- Source: NUC LiteLLM, PostgreSQL, Redis, CPA and their existing images.
- Deployment: `uv run ansible-playbook litellm-remote.yml`.

The dedicated playbook expects the private backup and its images to have already
been transferred. It restores PostgreSQL once, with a transaction and a completion
marker. It must not be used to overwrite an existing remote database. No key or
team reconciliation runs against either instance during restore.

## Verified deployment

- PostgreSQL dump: 1,653,483,629 bytes; source/destination SHA-256 matched.
- Restored 82 tables, including 65 keys, nine teams, four users and 38 permission
  objects. The latter four counts matched the source snapshot.
- HTTPS certificate verification and readiness succeeded from Hetzner.
- Daniel's existing managed key: 61 models, completed GPT-6.1 streaming response,
  215 discovered MCP tools and a successful `github-get_me` read.
- Anna's existing Docker key: 23 models, completed GPT-6.1 streaming response,
  20 discovered MCP tools; direct `github-get_me` denied. Unauthenticated model
  discovery returned HTTP 401.
- Anna's remote model call also passed with remote-container egress to
  `192.168.0.0/16` temporarily rejected. That test rule was removed afterwards.
  This tests backend independence; client DNS still needs the switching step below.
- A second `litellm-remote.yml` run reported `changed=0`.
- `/fallback/login` returns HTTP 200; interactive admin login was not tested.
- All five Docker agents and Daniel's bare-metal gateway were switched and restarted.
  Only the Hermes containers were recreated; their Tailscale sidecars were retained.

The existing Hermes egress policy now additionally permits only
`100.121.44.75:443` from each of the five Hetzner agent networks. Apply this narrow
network change with
`uv run ansible-playbook setup.yml --tags hermes-network --limit hetzner`.
It does not recreate agents. Other private destinations remain restricted.

## Snapshot and transfer

`scripts/litellm_remote_snapshot.py snapshot DIRECTORY`, run as root on the NUC,
captures runtime credentials privately, original configuration, CPA auth files,
the CA bundle, a consistent custom-format PostgreSQL dump and a Redis RDB snapshot.
It does not stop the source. The image IDs in `runtime.json` must also be exported
with `docker save` into `images.tar.gz`. On Dashserv, run
`litellm_remote_snapshot.py import-images DIRECTORY`: this supplies explicit tags
and uses the complete Docker manifest rather than Docker 28's incomplete OCI
index for untagged multi-image exports. Do not print the runtime file, since it
contains secrets. Transfer over verified SSH, retaining root-only permissions.

The destination keeps the original configuration in the backup. Its working copy
changes CPA routes to the local `cpa:8317`, disables home-hosted Phoenix callbacks,
uses the remote public base URL, and trusts only its dedicated Docker network for
forwarded MCP client addresses. MCP membership and model/key/team permissions
are preserved. Redis starts from the backup RDB with ordinary snapshot persistence.

PostgreSQL, Redis and CPA have no host ports. HTTPS and the LiteLLM backend port
bind only to the Tailnet IP. The proxy, CPA, HA-MCP and Caddy use the host split-DNS resolver through
`dns.override.yml`; Docker still resolves their internal service aliases. Internal
names resolve through the NUC Tailnet address, and public lookups go directly to
public resolvers. PostgreSQL and Redis retain their original DNS configuration. Caddy uses DNS-01 and its own
certificate storage. Regfish owns the public A record; Pi-hole's `dns_target`
override resolves this service directly to Dashserv instead of the NUC proxy.

## What remains unavailable when the house is offline

- Local inference, ASR/TTS, Home Assistant, Immich, n8n and AI-Lab media backends.
- Pocket ID login. API keys do not require Pocket ID; the remote instance omits
  OIDC settings and retains LiteLLM's local administrative login.
- Any other MCP backend hosted at home. Copying the gateway does not copy those
  applications.

## Cutover completed

Model-provider, central MCP, image generation and speech base URLs now point to
`litellm-remote.kirelabs.org`. Existing credentials, models, fallback order,
permissions and manual direct MCP entries were retained. Changes to manual Hermes
configuration used `hermes config set`.

The Hetzner host and all five network namespaces have a static remote hostname
mapping. The mapping is also persisted in Compose and Ansible. The host-specific
`hermes_litellm_base_url` selects Dashserv; other inventory groups retain the NUC.
Private pre-cutover config/environment/Compose backups are at
`/var/backups/hermes-cutover-20261021` on Hetzner.

Verification after the real NUC shutdown:

- NUC TCP ports 22 and 443 were unreachable from Hetzner; Dashserv 443 remained
  reachable. Dashserv's six containers stayed running, PostgreSQL healthy.
- All six real Hermes gateway APIs completed unique prompts with actual `terminal`
  tool execution. Their session databases recorded the tool calls. The five Docker
  agents are multipurpose, Marian, Nele, Anna and Sabine; the sixth is bare metal.
- Before shutdown, all six current configs had no remaining old LiteLLM URL. Model
  sessions recorded the remote billing base URL. Telegram was connected after
  startup, and Multipurpose's WhatsApp connection was restored.
- Anna also passed an actual gateway/model/tool request with her namespace's
  `192.168.0.0/16` egress blocked. The temporary firewall rule was removed.
- The bare-metal API test must load Hermes' native environment loader: its existing
  1Password integration overrides the managed API test credential. Using the
  native loader authenticated successfully without changing credentials.
- With the NUC off, external `fetch-fetch` MCP reads succeeded with all five
  Docker keys, and `github-get_me` succeeded with the main agent's actual runtime
  credential. Earlier permission-denial and unauthenticated-access tests passed.
- All six Telegram adapters remained connected after the real shutdown;
  Multipurpose's WhatsApp adapter remained connected too. No test messages were
  sent to people. Main Discord stayed in its pre-existing paused state.
- Repository playbook syntax and the two snapshot preparation unit tests passed.

The controller's LAN-to-Tailnet route also disappeared with the NUC. Management
remains possible through Dashserv, for example:
`ssh -J daniel@77.90.42.61 daniel@100.82.91.51`.

## Returning to the NUC

Bring the NUC back and verify its LiteLLM model/MCP endpoints first. Remove the
Hetzner override of `hermes_litellm_base_url` (or set it to the home URL). For the
manual bare-metal configuration, use `hermes config set` on
`providers.kirelabs-litellm.api`, `mcp_servers.litellm.url`,
`tts.openai.base_url`, `stt.openai.base_url`, `image_gen.openai.base_url`,
`OPENAI_BASE_URL` and `STT_OPENAI_BASE_URL`. Use `/v1` for all except MCP (`/mcp/`).
Apply the corresponding Docker configuration and environment changes, then restart
idle gateways. The private backups are available for selective recovery; avoid
blindly restoring them over later user changes. Remote host mappings can remain
until the temporary stack is retired.

Revert the endpoint settings to return to the NUC; do not restore the now-diverged
remote database over the source. CPA OAuth credentials are copied, not synchronized;
provider token refresh/rotation may require attention during a longer parallel run.

## DNS follow-up on 2026-10-23

`group_vars/all/internal_dns.yml` is the shared resolver/domain policy. Only the
NUC is enabled while the Pi is offline. `internal-dns.yml` installs a private
`dnsmasq-base` service on Dashserv, bound to loopback and the LiteLLM Docker bridge,
and applies a Compose DNS override to the four application containers. It leaves
the database containers untouched. Dashserv intentionally uses `accept-dns=false`
because Ansible owns its host and container resolver; it still accepts routes.
MagicDNS names are forwarded to `100.100.100.100`.

LAN DHCP now advertises only the active NUC resolver. Existing clients pick this
up on DHCP renewal. The `nopihole` client exception retains its public resolvers.
The Pi can be added to `internal_dns_resolvers` after it is online and validated.

The central Tailscale API reconciliation is applied through `tailscale-dns.yml`. It
uses a DNS-scoped OAuth token, PATCHes only managed suffixes and verifies unrelated
routes are preserved. After Daniel granted the existing OAuth client the `dns`
permission, the check and deployment succeeded. Both `lan` and `kirelabs.org` now
use the NUC's Tailnet DNS address `100.124.155.112`. The more-specific
`litellm-remote.kirelabs.org` route uses `1.1.1.1` and `8.8.8.8`, keeping cloud
gateway resolution independent of the home DNS server. No new secret was needed.

Validation: LAN and Hetzner name lookups passed; Dashserv host/container internal
and public resolution passed. A Hermes virtual key completed remote `home-tts`
(151644 WAV bytes, 2.4 seconds), followed by remote `home-asr` (0.4 seconds), with
the expected German transcription. A repeat `internal-dns.yml` run changed nothing.

With the resolver cache cleared and UDP/TCP DNS to the NUC temporarily rejected,
internal resolution failed as expected while the remote gateway/public names and
an actual GPT cloud completion succeeded. All temporary firewall rules were
removed and internal resolution was verified again afterwards.
