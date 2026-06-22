# TeslaMate Role

This role deploys [TeslaMate](https://docs.teslamate.org/) on `homelab-nuc` as a Docker Compose stack with:

- TeslaMate app container
- PostgreSQL database container
- TeslaMate Grafana container
- a dedicated `teslamate` Docker network

MQTT is expected to come from the existing Home Assistant/Mosquitto deployment.

## Configuration

Vault-managed values:

1. `teslamate_encryption_key` — generate with:
   ```bash
   openssl rand -base64 32
   ```
2. `teslamate_database_password` — database and Grafana admin password.

Ports come from `group_vars/all/config.yml`:

- TeslaMate host port: `{{ teslamate_http_port }}` (currently `8098`) → container port `4000`
- Grafana host port: `{{ grafana_http_port }}` (currently `3004`) → container port `3000`

Public HTTPS routes come from `group_vars/all/services.yml` and Caddy:

- TeslaMate: `https://teslamate.kirelabs.org`
- Grafana: `https://teslamate-grafana.kirelabs.org`

The role also updates TeslaMate's DB settings so `base_url` and `grafana_url` point at those HTTPS domains.

## Deployment

```bash
uv run ansible-playbook setup.yml --tags teslamate --limit homelab
```

If domains or ports in `services.yml` change, redeploy Caddy and Pi-hole as well so reverse proxy and DNS records are refreshed.
