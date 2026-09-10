# Uptime Kuma alerts in Hermes Projects

Kuma sends monitoring events directly over Tailscale to the main bare-metal
Hermes gateway at `100.82.91.51:8644/webhooks/uptime-kuma`. Hermes replies to
Telegram group `-1003552388158` (Projects), forum topic `3`.

The route performs brief read-only diagnosis for outages, confirms recoveries,
and only acknowledges test events. It does not authorize automatic repairs.
The existing Hermes subscriptions and personal `config.yaml` are preserved.

## Source of truth

- `group_vars/all/monitoring_hermes.yml`: endpoint, Telegram destination and prompt.
- `group_vars/all/monitoring_hermes_secrets.yml`: dedicated encrypted route secret.
- `roles/monitoring/defaults/main.yml`: AutoKuma notification `hermes-projects`.
- `roles/monitoring/templates/autokuma.toml.j2`: default notification for generated monitors.
- `monitoring-hermes-webhook.yml`: targeted, idempotent subscription and notification deployment.

Hermes accepts the shared secret through `X-Gitlab-Token`. The connection uses
the encrypted Tailnet path; no public proxy endpoint or signing adapter is
needed. Secrets are rendered only into protected runtime files with Ansible
output/diffs suppressed. The dynamic subscription is hot-reloaded without a
Hermes restart.

The webhook sends selected event fields, never the full monitor object, which
can contain authorization headers and other credentials. AutoKuma's Tera raw
block preserves the Liquid expressions that Kuma evaluates when sending.

## Deployment

```sh
uv run ansible-playbook monitoring-hermes-webhook.yml --syntax-check
uv run ansible-playbook monitoring-hermes-webhook.yml
```

Only AutoKuma restarts if its defaults change. Allow up to two 30-second sync
cycles for notification creation and monitor association. Existing unrelated
notification assignments must remain intact.

AutoKuma replaces the notification selection when defaults are supplied, so
the defaults explicitly retain Kuma IDs 1 and 3. Existing exceptions are
preserved: Borgmatic uses only ID 3, and `hermes-assist` previously had neither.
Hermes is added to all of these through `notification_name_list`. Future
AutoKuma monitors inherit Hermes; the notification is also a UI default for
manually created monitors.

Verify the Hermes notification is assigned to every monitor, unauthenticated
requests return HTTP 401, and a marked test event sent with Kuma's webhook
provider reaches Projects topic 3. Do not dump notification definitions or
monitor headers while checking.
