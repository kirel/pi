# Traefik Migration Guide

## Overview

Replace Caddy reverse proxy with Traefik for dynamic, Docker-native routing that automatically picks up configuration changes without restarts.

## Why Traefik vs Caddy

### Current Caddy Pain Points
- Requires Jinja2 template regeneration on services.yml changes
- Needs container restart to apply new routes
- File-based configuration
- Manual service discovery

### Traefik Benefits
- **Dynamic reloads**: Watches configuration files in real-time (no restarts)
- **Docker-native**: Can auto-discover services via labels OR use file provider
- **Mixed environment support**: Handles Docker containers, bare-metal services, and cross-host routing seamlessly
- **Built-in dashboard**: Web UI at port 8080 for monitoring
- **Flexible providers**: Docker, file, Kubernetes, Consul, etc.
- **Advanced routing**: Header-based, path-based, weighted load balancing

## Current Setup Analysis

### Services Requiring Cross-Host/Non-Docker Routing
From `group_vars/all/services.yml`:

**Cross-host Docker:**
- `glances-micpi` → `micpi.lan:61208` (different host)
- `ollama-ailab` → `ailab-ubuntu.lan` (AI lab server)

**Non-Docker/Bare-metal:**
- `proxmox` → `ailab-proxmox.lan:8006` (physical Proxmox server, nodocker: true)

**Standard Docker (same host):**
- Most services on `homelab-nuc` (homeassistant, jellyfin, portainer, etc.)

## Migration Strategy

### Phase 1: Hybrid Approach (Minimal Changes)
Keep `services.yml` as-is and generate Traefik's dynamic configuration file.

**Pros:**
- Minimal changes to existing structure
- Can migrate incrementally
- Backward compatible

**Cons:**
- Still using file-based config (less "Traefik-native")

**Implementation:**
1. Create Traefik role (replace Caddy)
2. Static config: Traefik daemon settings
3. Dynamic config: Generated from `services.yml`
4. File watcher enabled for auto-reload

### Phase 2: Native Docker Labels (Full Migration)
Convert each service to use Traefik labels in docker-compose.

**Pros:**
- Truly Docker-native
- Automatic service discovery
- No separate config file needed

**Cons:**
- Requires modifying all service roles
- Larger change set

## Implementation Plan

### Step 1: Create Traefik Role Structure

```
roles/traefik/
├── tasks/
│   └── main.yml              # Main installation/configuration
├── templates/
│   ├── traefik.yml.j2        # Static configuration
│   ├── dynamic.yml.j2        # Dynamic routing (generated from services.yml)
│   └── traefik.service.j2    # Systemd service override (optional)
├── handlers/
│   └── main.yml              # Reload handlers
├── defaults/
│   └── main.yml              # Default variables
└── vars/
    └── main.yml              # Traefik-specific variables
```

### Step 2: Static Configuration Template

**`roles/traefik/templates/traefik.yml.j2`:**
```yaml
api:
  dashboard: true
  insecure: true  # OK for homelab

entryPoints:
  web:
    address: ":80"
    {% if traefik_enable_ssl | default(true) %}
    forwardedHeaders:
      trustedIPs:
        - 127.0.0.1/32
        - 192.168.50.0/24
    {% endif %}
  websecure:
    address: ":443"

providers:
  docker:
    endpoint: "unix:///var/run/docker.sock"
    exposedByDefault: false
    network: traefik  # Use dedicated network
    {% if traefik_docker_swarm | default(false) %}
    swarmMode: true
    {% endif %}
  file:
    filename: /etc/traefik/dynamic.yml
    watch: true  # KEY: Enable file watching

certificatesResolvers:
  letsencrypt:
    acme:
      email: {{ traefik_acme_email }}
      storage: /acme.json
      {% if traefik_acme_staging | default(false) %}
      caServer: https://acme-staging-v02.api.letsencrypt.org/directory
      {% endif %}
      httpChallenge:
        entryPoint: web

log:
  level: INFO  # DEBUG for troubleshooting

accessLog: {}

metrics:
  prometheus:
    addEntryPointsLabels: true
    addServicesLabels: true
```

### Step 3: Dynamic Configuration Template

**`roles/traefik/templates/dynamic.yml.j2`:**
```yaml
http:
  routers:
{% for service_name, service in services.items() %}
{% if service.target is defined %}
  {{ service_name }}:
    rule: "Host(`{% if service.domain is defined %}{{ service.domain }}{% else %}{{ service_name }}.lan{% endif %}`)"
    service: "{{ service_name }}"
    entryPoints:
{% if service.tls_skip | default(false) %}
      - web
{% else %}
      - web
      - websecure
{% endif %}
{% if service.priority is defined %}
    priority: {{ service.priority }}
{% endif %}
{% endif %}
{% endfor %}

  services:
{% for service_name, service in services.items() %}
{% if service.target is defined %}
  {{ service_name }}:
    loadBalancer:
      servers:
        - url: "{{ 'https' if service.tls_skip | default(false) else 'http' }}://{{ service.target }}:{{ service.http_port }}{% if service.path is defined %}{{ service.path }}{% endif %}"
{% if service.health_check is defined %}
      healthCheck:
        path: {{ service.health_check }}
        interval: {{ service.health_check_interval | default('30s") }}
{% endif %}
{% if service.try is defined %}
      failover:
        tryCount: {{ service.try | regex_replace('s$', '') | int }}
{% endif %}
{% if service.load_balancer is defined %}
      {{ service.load_balancer | to_nice_yaml | indent(8) }}
{% endif %}
{% endif %}
{% endfor %}

tcp:
  routers:
{% for service_name, service in services.items() %}
{% if service.tcp is defined %}
  {{ service_name }}:
    rule: "HostSNI(`{% if service.domain is defined %}{{ service.domain }}{% else %}{{ service_name }}.lan{% endif %}`)"
    service: "{{ service_name }}"
    entryPoints: ["{{ service.tcp.entrypoint | default('websecure') }}"]
{% endif %}
{% endfor %}

  services:
{% for service_name, service in services.items() %}
{% if service.tcp is defined %}
  {{ service_name }}:
    loadBalancer:
      servers:
        - address: "{{ service.target }}:{{ service.tcp.port }}"
{% endif %}
{% endfor %}
```

### Step 4: Main Tasks File

**`roles/traefik/tasks/main.yml`:**
```yaml
---
- name: Create traefik user
  user:
    name: traefik
    system: true
    shell: /bin/false
    home: /var/lib/traefik
    create_home: true

- name: Ensure traefik directories exist
  file:
    path: "{{ item }}"
    state: directory
    owner: traefik
    group: traefik
    mode: '0755'
  loop:
    - /etc/traefik
    - /var/lib/traefik
    - "{{ traefik_config_dir | default('/opt/traefik') }}"

- name: Install Traefik
  get_url:
    url: "https://github.com/traefik/traefik/releases/download/{{ traefik_version }}/traefik_{{ traefik_version }}_linux_amd64.tar.gz"
    dest: "/tmp/traefik.tar.gz"
    checksum: "sha256:{{ traefik_checksum }}"

- name: Extract Traefik binary
  unarchive:
    src: "/tmp/traefik.tar.gz"
    dest: "/usr/local/bin"
    extra_opts: ["--strip-components=1"]
    creates: /usr/local/bin/traefik

- name: Set permissions on traefik binary
  file:
    path: /usr/local/bin/traefik
    mode: '0755'

- name: Template static configuration
  template:
    src: traefik.yml.j2
    dest: /etc/traefik/traefik.yml
    owner: traefik
    group: traefik
    mode: '0600'
  notify: reload traefik

- name: Template dynamic configuration
  template:
    src: dynamic.yml.j2
    dest: /etc/traefik/dynamic.yml
    owner: traefik
    group: traefik
    mode: '0600'
  notify: reload traefik

- name: Create acme.json for Let's Encrypt
  copy:
    content: "{}"
    dest: /var/lib/traefik/acme.json
    owner: traefik
    group: traefik
    mode: '0600'
  when: traefik_enable_ssl | default(true)

- name: Create Traefik network
  community.docker.docker_network:
    name: traefik
    state: present
    ipam_config:
      - subnet: 172.20.0.0/16

- name: Template systemd service file
  template:
    src: traefik.service.j2
    dest: /etc/systemd/system/traefik.service
  notify:
    - systemd daemon-reload
    - restart traefik

- name: Ensure traefik is running
  systemd:
    name: traefik
    state: started
    enabled: true
    daemon_reload: true

- name: Wait for Traefik to be ready
  uri:
    url: "http://localhost:8080/ping"
    status_code: 200
  register: traefik_ping
  retries: 30
  delay: 2
  until: traefik_ping is succeeded
```

### Step 5: Handlers

**`roles/traefik/handlers/main.yml`:**
```yaml
---
- name: reload traefik
  systemd:
    name: traefik
    state: reloaded

- name: restart traefik
  systemd:
    name: traefik
    state: restarted

- name: systemd daemon-reload
  systemd:
    daemon_reload: true
```

### Step 6: Variables

**`roles/traefik/defaults/main.yml`:**
```yaml
---
traefik_version: "v3.0.0"
traefik_checksum: "sha256_checksum_here"  # Get from Traefik releases
traefik_acme_email: "admin@example.com"
traefik_acme_staging: false
traefik_enable_ssl: true
traefik_docker_swarm: false
```

**`group_vars/all/traefik.yml`:**
```yaml
---
# Add to existing group_vars or create new file

traefik_service:
  name: Traefik
  target: homelab-nuc.lan
  http_port: 8080
  domain: traefik.lan
  group: Monitoring
  icon: traefik.png
```

### Step 7: Update setup.yml

**In `setup.yml`, replace:**
```yaml
    - caddy
```
**With:**
```yaml
    - traefik
```

### Step 8: Service-Specific Considerations

#### For `nodocker: true` services (like Proxmox)
No changes needed - Traefik can route to any backend.

#### For cross-host services
Just ensure firewall allows Traefik host to reach target hosts on specified ports.

#### For TLS passthrough
Already handled via `tls_skip` option in services.yml.

#### For proxy ports (like Ollama)
Current config has both `proxy_port` and `http_port` - use `http_port` for Traefik routing.

## Testing & Validation

### Before Stopping Caddy
1. Test Traefik config:
   ```bash
   uv run ansible-playbook setup.yml --tags traefik --limit homelab --check
   ```

2. Verify Traefik starts:
   ```bash
   ssh nuc "systemctl status traefik"
   ```

3. Check dashboard:
   ```bash
   curl -I http://homelab-nuc.lan:8080
   ```

4. Test one route:
   ```bash
   curl -I http://homeassistant.lan
   ```

5. Verify logs:
   ```bash
   ssh nuc "journalctl -u traefik -f"
   ```

### Migration Steps
1. Deploy Traefik alongside Caddy
2. Verify all routes work in Traefik
3. Update DNS/hosts file if needed (should work same as Caddy)
4. Stop and disable Caddy
5. Remove Caddy containers
6. Update setup.yml to remove Caddy tag

## Rollback Plan

If issues occur:
1. Stop Traefik: `systemctl stop traefik`
2. Start Caddy: `docker start caddy`
3. Restore `setup.yml` to use Caddy
4. Re-run playbook with Caddy tag

## Future Enhancements

### Phase 2: Native Docker Labels
Once comfortable with Traefik, migrate individual services to use labels:

**Example service label migration:**
```yaml
# In service's docker-compose.yml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.homeassistant.rule=Host(`ha.lan`)"
  - "traefik.http.services.homeassistant.loadbalancer.server.port=8123"
  - "traefik.http.routers.homeassistant.tls.certresolver=letsencrypt"
```

Benefits:
- No separate dynamic.yml needed
- Automatic service discovery
- No config file regeneration

### Middleware Options
Add custom middleware for services:
- Rate limiting
- Authentication (basic, OAuth, JWT)
- Redirect to HTTPS
- Custom headers
- Compression

### Monitoring Integration
- Prometheus metrics endpoint
- Grafana dashboards
- Health check endpoints
- Access logs analysis

## References

- [Traefik Documentation](https://doc.traefik.io/traefik/)
- [Traefik Docker Provider](https://doc.traefik.io/traefik/providers/docker/)
- [Traefik File Provider](https://doc.traefik.io/traefik/providers/file/)
- [Traefik Routing Configuration](https://doc.traefik.io/traefik/routing/routers/)
- [Traefik Service Configuration](https://doc.traefik.io/traefik/routing/services/)

## Checksums for Traefik Versions

Get latest checksums:
```bash
# Example for v3.0.0
curl -L https://github.com/traefik/traefik/releases/download/v3.0.0/traefik_v3.0.0_checksums.txt
```

## Inventory Updates Needed

**No changes required** - Traefik uses same `services.yml` structure.

## Service Network Requirements

**Create dedicated Traefik network:**
- Name: `traefik`
- Subnet: `172.20.0.0/16` (custom, not overlapping existing)

All services that need Traefik routing should connect to this network.

## Security Considerations

### Dashboard Access
- Default: `http://homelab-nuc.lan:8080` (insecure, for homelab OK)
- For production: Enable auth, use API key, or restrict by IP

### ACME Let's Encrypt
- For .lan domains: Use `tls_skip: true` (no Let's Encrypt)
- For public domains: Enable Let's Encrypt with staging first

### Access Control
- Use Traefik middleware for basic auth
- Consider OAuth for sensitive services
- SSL/TLS certificate management automatic

## Monitoring

### Health Checks
- Built-in: `curl http://localhost:8080/ping`
- Dashboard: `http://homelab-nuc.lan:8080/dashboard/`

### Metrics
- Prometheus format: `http://homelab-nuc.lan:8080/metrics`
- Can be scraped by Glances or Prometheus

### Logs
```bash
journalctl -u traefik -f
docker logs -f traefik
```

## Performance Notes

- File watcher: Low overhead, uses inotify
- No performance penalty vs Caddy
- Can handle 100+ routes easily
- Memory usage: ~50-100MB typical
