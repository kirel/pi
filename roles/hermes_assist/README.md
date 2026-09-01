# Hermes Assist

This role runs Daniel's private Home Assistant voice gateway on
`homelab-nuc`. It is deliberately isolated from the shared Home Assistant:

- separate Compose project, container, network, and config directory
- fixed `172.16.50.0/24` Docker subnet to avoid Tailnet route overlap
- no host networking, privileged mode, devices, D-Bus, or shared volumes
- HTTP is bound to `127.0.0.1` for access through host-networked Caddy only
- the Home Assistant config directory is mode `0700` because it contains the
  Hermes API credential after UI setup
- Local OpenAI LLM is installed from a pinned, checksummed release

The role owns only the container and its bootstrap configuration. It does not
write Home Assistant `.storage`, create users, or configure integrations and
Assist pipelines. Those are created through Home Assistant config flows after
onboarding.

## Deployment

```bash
uv run ansible-playbook setup.yml --tags hermes-assist --limit homelab
```

For the initial onboarding, create an SSH tunnel and browse to
`http://127.0.0.1:8124`:

```bash
ssh -N -L 8124:127.0.0.1:8124 root@homelab-nuc.lan
```

Create only Daniel's account. Then open **Settings -> System -> Network ->
HTTP server**, enable **Trust X-Forwarded-For**, and add `172.16.50.1` as the
trusted proxy. Save, wait for Home Assistant to restart, browse to
`https://hermes-assist.kirelabs.org`, and confirm the new HTTP settings within
five minutes. Home Assistant 2026.8 owns these settings in its UI and ignores
an Ansible-managed `http:` YAML block after the one-time migration.

The route intentionally remains private; no `public: true` service flag is
configured.

## UI configuration boundary

Configure these through **Settings -> Devices & services**:

1. Wyoming Protocol at `ailab-ubuntu.lan:10300` for STT and TTS.
2. Local OpenAI LLM as a generic OpenAI-compatible backend using
   `http://100.82.91.51:8642/v1`, model `hermes-agent`, and the private Hermes
   API key from the bare-metal `.env`/Vault configuration.
3. Do not select a Home Assistant LLM API or expose entities. Hermes executes
   its own trusted tools server-side.
4. Create a dedicated Assist pipeline using the configured STT, conversation,
   and TTS providers.

The Hermes API listener and key are owned by `hermes_baremetal`. Wyoming
remains owned by `wyoming_openai`. Private routing remains owned by
`group_vars/all/services.yml`, Caddy, and Pi-hole.
