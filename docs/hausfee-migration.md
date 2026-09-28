# Hausfee

Deployed and verified on 2026-09-13.

## Agreed behavior

Hausfee is one bot with one profile and one shared memory across all channels.
The Docker agent ID remains `multipurpose`; its single default profile is displayed
as Hausfee. Do not introduce separate group/admin profiles or reduced group tools.

- WhatsApp group: **Sabine, Daniel & die Hausfee 🧚**, ID `{{ hermes_hausfee_group_id }}`.
- Daniel's and Sabine's WhatsApp DMs, plus Daniel's Telegram DM, reach the same Hausfee. DMs keep technical
  conversations out of the group; they do not confer additional capabilities.
- Daniel and Sabine share the group conversation. Hausfee responds to mentions,
  replies and commands. Ordinary unaddressed conversation is ignored.
- Accepted group messages and DMs have identical tool and command privileges,
  including shell, files, browser, skills, delegation and configuration inside
  the container. Chat threads are separate; persistent memory and searchable
  history belong to the same profile.
- Infrastructure outside this container remains with Daniel's personal
  bare-metal Hermes. Sabine's personal bot is separate and unchanged.

WhatsApp was paired successfully. Live group metadata and identity mapping match
Daniel, Sabine and the bot. Telegram remains `@multipurpose_hermes_bot`, with display
name Hausfee. The invitation link is not stored in the repository.

## Configuration and deployment

`group_vars/all/hermes_hausfee.yml` defines identity, channel policies and behavior.
`group_vars/hetzner.yml` enables it and declares environment and LiteLLM permissions.

```bash
uv run ansible-playbook setup.yml --tags hausfee --limit ubuntu-8gb-fsn1-1
```

This updates only the existing bot's LiteLLM key and restarts only
`hermes-multipurpose` when configuration or ownership changes. The second run
completed with `changed=0`.

The mistakenly introduced secondary profile was retired. Its short conversation
was imported into the default database using column-name-based mapping. The old
profile is archived under `/opt/data/archives/retired-hausfee-*`. Original configuration
is backed up outside the container in the deployment's `hausfee-migration-backup`
directory. No named profile or profile routing remains active.

## Integrations

- LiteLLM chat: `gpt-6-astra-cpa`, followed by the configured Gemini and two GLM
  fallbacks. All four returned successful completions.
- MCP permissions: `web`, `maps`, `home_control`, `shopping`, including the
  existing seven-tool Todoist allowlist. No infrastructure permissions were added.
- Shopping targets the shared Todoist project `Einkaufsliste`
  (`6Jhc7FCRmrMQPgW7`). This is the workflow target; the tool allowlist itself
  does not enforce a project boundary. The older shared skill mentions unavailable
  `get_overview`; Hausfee's managed instructions use project-scoped `find_tasks`
  with pagination instead.
- Skills come from the bot's own library and mounted global, family, household and
  caddy-proxy directories. A real agent turn successfully loaded `einkaufsliste`.
- The managed shell initialization restores the persistent npm CLI path after
  login-shell startup. Cache ownership was corrected. Actual agent tools ran
  `gws --version` and opened `example.com` in the browser.

## Google login deferred

Use `gws` with **hausfee.kirsch@gmail.com** and Drive resources shared with that
account. `gws 0.22.5` is installed at `/opt/data/npm-global/bin/gws`.
`GOOGLE_WORKSPACE_CLI_CONFIG_DIR=/opt/data/.config/gws` also applies in the agent shell.

The existing desktop OAuth client was transferred securely from the Hetzner host
to that directory's `client_secret.json`. Personal Google user credentials were
not copied. Hermes can read the client; `gws auth status` reports no user login.
Daniel explicitly deferred login until he is at a suitable computer. After consent,
verify account identity and a shared Drive resource. Gmail/calendar access is not
implied by possession of the account address.

## Verification

- One gateway process and profile, no profile routes; equal native toolsets and
  no additional slash-command gate for the group.
- WhatsApp connected, gateway health HTTP 200, Telegram identity valid.
- Intake tests passed for Daniel's DM, household group, unrelated sender/group
  rejection and mention behavior. Sabine participates through the group; her
  separate WhatsApp DM is now also permitted with the same tools and shared memory.
- LiteLLM/OpenAI/voice credentials accepted. Direct Tavily and Home Assistant
  credentials returned HTTP 200. Gateway API authentication: absent/invalid key
  returned 401; configured key returned 200.
- MCP discovery: 64 tools. Read calls succeeded for Fetch, Google Maps, Tavily,
  Home Assistant live state/date and Todoist sections/tasks. Mutating MCP
  operations were not executed merely for testing.
- Real gateway turns executed terminal, skill_view and browser_exec. Speech
  generation and transcription both returned HTTP 200.
- Ansible syntax, whitespace checks, migration/idempotence tests and the second
  live deployment passed. A new message from each messenger is the remaining
  user-side delivery check; no unsolicited test messages were sent.

## Shared writable household skills

`/home/daniel/projects/agent-skills/skills/household` is the shared source.
Bare-metal Hermes already loads it through `~/.agents/skills/household`.
Hausfee mounts that same directory at `/skills/household` with `read_only: false`
and uses it as `skills.create_dir`. Existing household skills are edited in place.
All Hausfee channels have the same access.

External mounts remain read-only by default. `writable-skills.yml` grants access
and inherited directory ACLs to host user `daniel` and container UID 10000.
Writable roots are excluded from the legacy ownership/0755 normalization.
Skill writers using explicit 0644 modes can limit direct in-place writes by the
other UID; Hermes' atomic replacement remains possible through writable parent
folders. Do not add private credentials to the skills repository.

Deploy the permissions, Compose mount and Hausfee configuration with:

```bash
uv run ansible-playbook setup.yml --tags hermes-skills,hausfee --limit ubuntu-8gb-fsn1-1 --extra-vars '{"hermes_docker_deploy_services":["hermes-multipurpose"]}'
```

The scoped handler reuses the existing image and only reconciles Hausfee, without
its dependencies or other agents. Ordinary full deployments retain their existing
build behavior. The skills repository keeps its existing skip-update-if-dirty
behavior; no automatic commit or push is introduced.

Verified live: `hausbau-kontext` is discoverable; Hausfee created a temporary skill,
the bare-metal runtime user edited it, and Hausfee patched it with `skill_manage`.
Host-created files also accepted shell writes from Hausfee. The temporary skill
was removed and the shared Git checkout remained clean. Gateway health returned
200 and WhatsApp reported connected. The final reconciliation reported
`changed=0, failed=0`; peer containers retained their IDs. Scoped deployments flush
the Compose handler before reconciling Hausfee configuration so container startup
cannot overwrite the final managed settings.

## 1Password CLI

Hausfee has `op` 2.38.1 under `/opt/data/.local/lib/1password/op`, with an
`/opt/data/.local/bin/op` wrapper that loads its own service-account token for
that process. The existing agent shell initialization includes this directory.
The binary and credential persist across container recreation.

Ansible resolves only `op://homelab/y2h5jcyffdhf2pn4syn6rebxk4/credential` through
Ailab's authenticated `op-sa`. The transfer goes directly from Ailab to the
container over SSH stdin; the controller receives no token value. The token is
owned by Hermes with mode 0600 inside a 0700 directory. The pinned CLI binary
comes from Ailab's existing package installation; the reconciler checks the
version before transfer. Service-account permissions remain those configured
in 1Password. No interactive `op signin` is required.

```bash
uv run ansible-playbook setup.yml --tags hausfee-onepassword --limit ubuntu-8gb-fsn1-1
```

Authentication is checked with `op user get --me`, with output suppressed.
