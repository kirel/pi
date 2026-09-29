# Regfish DNS

Public authoritative DNS is declared in Ansible. API calls use the existing
Vault-encrypted `regfish_token` through `ansible.builtin.uri` on the controller.
No extra collection, daemon or provider SDK is required.

## Where a record belongs

| Declaration | Purpose |
| --- | --- |
| `services.<service>.domain` | Existing Caddy hostname and local Pi-hole CNAME |
| `services.<service>.dns` | Optional Regfish record for that same hostname |
| `services.<service>.public` | Existing Caddy access policy; independent of DNS |
| `regfish_dns_zones` in `group_vars/all/regfish_dns.yml` | Mail, external websites, apex records and wildcards |
| `additional_dns_entries` in `group_vars/all/dns.yml` | Additional local Pi-hole host records |

Add a Regfish record next to a service, without repeating its hostname:

```yaml
services:
  jellyfin:
    domain: jellyfin.kirelabs.org
    target: homelab-nuc.lan
    http_port: "{{ jellyfin_http_port }}"
    public: true
    dns:
      type: CNAME
      data: "{{ regfish_dns_home_target }}"
      # ttl: 600 is the default
```

An absent `dns` block means no Regfish record is managed for this service.
`public: true` never implicitly publishes a DNS record, and `dns` never changes
Caddy's access policy. Do not derive public DNS from `target`: that is the
reverse proxy's backend, not necessarily the address clients should connect to.

The zone is inferred from `domain` using the longest matching key in
`regfish_dns_zones`. Declare a new zone there explicitly (an empty list is valid).
DNS aliases that are not the service's `domain` belong in the zone list; adding
a DNS alias alone does not add a Caddy virtual host or certificate.

## Public, local and Tailscale

- **Internet:** Regfish points at a public IP or hostname (currently ASUS DDNS
  for the four public homelab services). Caddy's `public` flag, routing, firewall
  and service authentication independently determine access.
- **Local only:** omit `dns`; Pi-hole continues to resolve the service locally.
- **Tailscale:** a Regfish A record can point at a `100.x` Tailscale address.
  The hostname/IP is publicly visible, but connecting requires Tailscale access
  and matching ACLs. The existing Hermes wildcard records use this pattern.
  Their IPs reference the existing Hetzner host variables instead of duplicating them.
- **Split DNS:** Pi-hole may override the same Regfish hostname internally.
  Service CNAMEs currently point at `homelab-nuc.lan`, where the shared Caddy
  runs. The public DNS target does not change this existing local route.

## Normal workflow

```bash
# Read the live API and print the plan; no writes, including in --check mode.
uv run ansible-playbook regfish-dns.yml --check

# Apply only planned changes and verify the result through the API.
uv run ansible-playbook regfish-dns.yml

# The same role is also part of setup.yml, once on the controller.
uv run ansible-playbook setup.yml --tags regfish-dns --limit homelab
```

The dedicated playbook needs controller internet access and the repository's
Vault password, but no SSH connection to the homelab host. Authentication tasks
use `no_log` and disable diffs; the displayed plan contains DNS data, never the key.
After editing `services.yml`, also deploy Caddy and both Pi-holes as usual.

## Record syntax and ownership

```yaml
regfish_dns_zones:
  example.org:
    - name: '@'                 # apex; relative names or in-zone FQDNs also work
      type: MX
      data: mail.example.org.  # hostname data is always absolute
      priority: 10
      ttl: 86400
    - name: '*.agent'
      type: A
      data: '100.82.91.51'
```

Supported types: A, AAAA, CNAME, ALIAS, MX, TXT and CAA. CAA requires `flags`
and `tag`; MX requires `priority`. TXT data is preserved verbatim. Names and
hostname-valued data get a trailing dot automatically. TTL defaults to 600;
imported TTLs are explicit and preserved. Unknown fields and duplicate records
(including duplicates across the zone list and services) fail before writes.

The default `state: present` creates missing records or updates an existing one.
Matching uses name/type/data first. For a single declared and existing record
at a name/type, changing `data` updates it in place. Multi-value record sets
need an `id` to change a particular value unambiguously; the imported apex A
records already carry these IDs. IDs are checked against name/type. A missing
explicit ID fails instead of silently recreating something; inspect the live
state, then remove/update the ID deliberately if restoration is needed.

**No automatic purge:** removing YAML does not delete a DNS record. It appears
under `unmanaged` in the next plan. To delete, retain the declaration with
`state: absent`, review `--check`, apply, then remove that declaration. Deletion
matches the exact data or explicit ID, never an arbitrary same-name record.
To rename a record, explicitly retire the old name and declare the new one.
CNAME/type migrations that conflict require separate reviewed steps.

`state: observed` records are inventory only. Their expected data, `auto` and
`active` flags are compared and discrepancies appear under `observed_drift`.
They are never created, updated or deleted. This preserves provider-owned
records and disabled legacy records; the REST record write schema does not
expose `auto`/`active`. A managed declaration that resolves to an automatic or
inactive live record fails rather than taking it over.

`_acme-challenge` records remain Caddy-owned and cannot be declared here.
SOA, provider NS records, delegation, DNSSEC, forwarding settings and domain
contracts are outside this record role. Unknown live records are reported,
never deleted. Do not run concurrent writers for the same managed record.

## Initial adoption: 2026-09-29

All eight existing zones were read. The record API returned 64 records:
35 managed, 10 observed (automatic and/or inactive), and 19 ACME TXT records.
Four service CNAMEs are declared in `services.yml`; the other 41 non-ACME
records are in `regfish_dns.yml`. Values, TTLs, MX priorities and annotations
were preserved. No record cleanup, activation or DNSSEC change is part of adoption.

```bash
uv run python -m unittest discover -s tests -p test_regfish_dns.py
```

API references: [record creation](https://docs.regfish.com/en/reference/dns/add-record/),
[updates by ID](https://docs.regfish.com/en/reference/dns/patch-record-by-rrid/),
[desired-state workflow](https://docs.regfish.com/en/recipes/dns-desired-state-sync/).
