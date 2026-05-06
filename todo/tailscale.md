# Tailscale + Pi-hole DNS Implementation Plan

Goal: use Tailscale in the homelab so Tailnet clients can resolve existing Pi-hole local DNS records while keeping MagicDNS enabled.

## Decisions

- Subnet routers: `nameserver-pi` and `homelab-nuc`
- Tailscale hosts managed by Ansible: only `nameserver-pi` and `homelab-nuc`
- Authentication: Tailscale OAuth client secret, stored via Ansible Vault
- DNS mode: Split DNS
- Tailscale Admin Console / DNS / route approval: manual ClickOps for now
- Pi-hole DNS binding: okay to bind port 53 on all host interfaces
- Advertised LAN route: only `192.168.50.0/24`
- Ignore previous `192.168.8.0/24` travel-router experiment for now

## Target Architecture

```text
Tailnet client
  -> MagicDNS for Tailnet hostnames
  -> Split DNS for lan + kirelabs.org
  -> Pi-hole via Tailscale IP of nameserver-pi/homelab-nuc
  -> DNS answers return 192.168.50.x addresses
  -> Tailscale subnet route reaches 192.168.50.0/24
```

Expected DNS behavior:

```text
nameserver-pi              -> MagicDNS / Tailscale 100.x address
homelab-nuc                -> MagicDNS / Tailscale 100.x address
nameserver-pi.lan          -> Pi-hole -> 192.168.50.4
homelab-nuc.lan            -> Pi-hole -> 192.168.50.5
*.kirelabs.org             -> Pi-hole CNAME/service records
```

## Prerequisites in Tailscale Admin Console

### 1. Create tag

Use:

```text
tag:homelab
```

ACL snippet example:

```json
{
  "tagOwners": {
    "tag:homelab": ["autogroup:admin"]
  }
}
```

### 2. Create OAuth client

Create an OAuth client with at least the `auth_keys` scope.

Store the client secret in Ansible Vault as:

```yaml
vault_tailscale_oauth_client_secret: "tskey-client-..."
```

Use OAuth instead of normal auth keys because normal auth keys expire after at most 90 days. OAuth client secrets are better suited for repeatable Ansible runs.

## Repository Changes

### 1. Update `requirements.yml`

Add collections:

```yaml
collections:
  - name: community.docker
  - name: community.general
  - name: artis3n.tailscale
```

Install with:

```bash
uv run ansible-galaxy collection install -r requirements.yml
```

### 2. Add Tailscale variables

Create `group_vars/all/tailscale.yml`:

```yaml
---
tailscale_lan_cidr: "192.168.50.0/24"
tailscale_tags:
  - homelab

tailscale_oauth_ephemeral: false
tailscale_oauth_preauthorized: true

tailscale_args: "--accept-dns=false --advertise-routes={{ tailscale_lan_cidr }}"
tailscale_authkey: "{{ vault_tailscale_oauth_client_secret }}"
```

Notes:

- The `artis3n.tailscale.machine` role requires `tailscale_tags` when using OAuth.
- Tags are specified without `tag:`; the role converts `homelab` to `tag:homelab`.
- `tailscale_oauth_ephemeral: false` is important for persistent homelab servers.
- `--accept-dns=false` prevents the servers from replacing their own DNS config with Tailnet DNS.
- `--advertise-routes=192.168.50.0/24` makes both selected hosts subnet routers.

### 3. Add vaulted secret

In `group_vars/all/secrets.yml` or equivalent vault-managed file:

```yaml
vault_tailscale_oauth_client_secret: "tskey-client-..."
```

### 4. Add role to `setup.yml`

Add `artis3n.tailscale.machine` to both the `homelab` and `nameserver` plays, before Docker/Pi-hole roles.

For `homelab`:

```yaml
- role: artis3n.tailscale.machine
  become: true
  tags: [tailscale]
```

For `nameserver`:

```yaml
- role: artis3n.tailscale.machine
  become: true
  tags: [tailscale]
```

### 5. Enable IP forwarding

Subnet routing requires IP forwarding. Add either a tiny local role, e.g. `roles/tailscale_router`, or tasks near the Tailscale role.

Recommended local role: `roles/tailscale_router/tasks/main.yml`

```yaml
---
- name: Enable IPv4 forwarding for Tailscale subnet routing
  ansible.posix.sysctl:
    name: net.ipv4.ip_forward
    value: "1"
    state: present
    reload: true

- name: Enable IPv6 forwarding for Tailscale
  ansible.posix.sysctl:
    name: net.ipv6.conf.all.forwarding
    value: "1"
    state: present
    reload: true
```

Then add it after the Tailscale role on `homelab` and `nameserver`:

```yaml
- { role: tailscale_router, become: true, tags: [tailscale] }
```

### 6. Adjust Pi-hole DNS port binding

In `roles/pihole/tasks/main.yml`, change Pi-hole port mappings from LAN-IP-only binding:

```yaml
- "{{ ansible_default_ipv4.address }}:53:53/tcp"
- "{{ ansible_default_ipv4.address }}:53:53/udp"
```

to all-interface binding:

```yaml
- "53:53/tcp"
- "53:53/udp"
```

Existing Pi-hole setting already fits Tailnet DNS:

```yaml
FTLCONF_dns_listeningMode: all
```

This lets Pi-hole answer DNS on both LAN IPs and Tailscale 100.x IPs.

## Deployment Steps

### 1. Install Ansible collections

```bash
uv run ansible-galaxy collection install -r requirements.yml
```

### 2. Deploy Tailscale to both routers

```bash
uv run ansible-playbook setup.yml --tags tailscale --limit nameserver,homelab
```

### 3. Redeploy Pi-hole

Because Pi-hole port bindings changed:

```bash
uv run ansible-playbook setup.yml --tags pihole --limit nameserver,homelab
```

### 4. Manual Tailscale Admin Console steps

Approve subnet routes for both machines:

```text
Machines -> nameserver-pi -> Route settings -> Approve 192.168.50.0/24
Machines -> homelab-nuc   -> Route settings -> Approve 192.168.50.0/24
```

Enable MagicDNS:

```text
DNS -> MagicDNS -> enabled
```

Configure Split DNS nameservers. Use the Tailscale IPs of both Pi-hole hosts as nameservers:

```text
DNS -> Nameservers -> Add nameserver
  100.x.y.z  # nameserver-pi Tailscale IP
  100.a.b.c  # homelab-nuc Tailscale IP

Split DNS domains:
  lan
  kirelabs.org
```

Do not enable global DNS override for now.

## Validation

Get Tailscale IPs:

```bash
ssh daniel@nameserver-pi.lan tailscale ip -4
ssh root@homelab-nuc.lan tailscale ip -4
```

From a Tailnet client:

```bash
dig nameserver-pi.lan
dig homelab-nuc.lan
dig jellyfin.kirelabs.org
ping 192.168.50.4
ping 192.168.50.5
curl -I https://pihole-nameserver.kirelabs.org
```

On Linux Tailnet clients, ensure routes are accepted:

```bash
sudo tailscale up --accept-routes
```

Expected:

- MagicDNS short names resolve for the two Tailscale machines.
- `*.lan` and `*.kirelabs.org` resolve through Pi-hole.
- `192.168.50.0/24` addresses are reachable remotely.
- If one subnet router is down, the other can still provide route/DNS when Tailscale has both nameservers/routes configured.

## Rollback

Disable advertised route:

```yaml
tailscale_args: "--accept-dns=false"
```

Then redeploy:

```bash
uv run ansible-playbook setup.yml --tags tailscale --limit nameserver,homelab
```

Optionally revert Pi-hole port bindings to LAN-IP-only if Tailnet DNS is no longer needed.
