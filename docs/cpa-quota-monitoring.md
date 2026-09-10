# CPA OpenAI and Google quota monitoring

Uptime Kuma's `CPA OpenAI Restquote (%)` HTTP JSON Query monitor calls CPA
directly every 300 seconds. No polling script or Usage Keeper session is needed.
AutoKuma owns the monitor through its static file provider.

Configuration lives in `roles/monitoring/defaults/main.yml`:

- `monitoring_cpa_codex_auth_index`: CPA's stable credential index. Update it
  when replacing the OpenAI account; new accounts are not discovered automatically.
- `monitoring_cpa_quota_min_remaining`: minimum healthy percentage, initially 20.
- `monitoring_cpa_quota_notifications`: existing Kuma notification IDs 1
  (Home Assistant Alarm) and 3 (Mein Telegram Alarm).

CPA's management `api-call` endpoint fetches `wham/usage` with server-side OAuth
token substitution. The JSONata expression returns the lowest remaining
percentage across the returned primary and secondary windows. Window duration
comes from OpenAI; a primary window is not necessarily a five-hour window.
Missing secondary windows are supported. Invalid/missing quota data, expired
reset times, upstream failures and explicitly blocked accounts fail the check.

Healthy means remaining quota is at least 20 percent. A failed check is retried
after 60 seconds before notification. Recovery uses the same threshold; there
is no separate hysteresis threshold. API errors also trigger the monitor.

The CPA management key comes from Ansible Vault. The rendered AutoKuma JSON
files have mode `0600`; rendering suppresses output and diffs. Kuma stores the
request authorization in its own database. Do not print monitor headers or
export complete monitor definitions into logs or chat.

Deploy only the static monitor configuration, without restarting services:

```sh
uv run ansible-playbook setup.yml --syntax-check
uv run ansible-playbook setup.yml --tags monitoring-config --limit homelab
```

Allow one AutoKuma sync interval (30 seconds), then check Kuma for an active
JSON Query monitor, the measured remaining percentage and both notification
assignments. A live healthy check does not itself test notification delivery.

The expression was checked against the running Kuma engine with single and
dual windows, the exact threshold, low remaining quota, missing windows,
missing percentages, an invalid second window, expired reset times, blocked
accounts and an upstream error.

## Google / Antigravity

`CPA Google Restquote (%)` uses the same threshold, polling interval, retry and
notification selections as OpenAI, including the default Hermes notification.
It checks every returned model group (currently Gemini and Claude/GPT), taking
the lowest remaining percentage across their weekly and five-hour buckets.
Every group must contain both windows. Missing fractions, invalid values,
missing or expired reset times and upstream failures fail the check.

The request goes through CPA `POST /v0/management/api-call` with server-side
`$TOKEN$` substitution to
`https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary`.
`monitoring_cpa_google_auth_index` and `monitoring_cpa_google_project_id` identify
the account and project; update them when replacing the Google account.
These identifiers are not credentials. The management key remains vaulted.

On 2026-09-07 the Daily endpoint returned both weekly and 5h quota buckets.
The production endpoint returned HTTP 403 `SUBSCRIPTION_REQUIRED` for the same
account. The older `fetchAvailableModels` endpoint returned model quotas but
did not expose both windows, so it is not used as a fallback.

The expression was tested in the running Kuma JSONata engine for healthy
responses, exactly 20 percent, low third-party quota, zero quota, missing windows,
missing/out-of-range fractions, expired resets, empty groups and upstream errors.
No synthetic alerts were sent to notification channels.
