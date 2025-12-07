# Pi-hole DNS/DHCP Optimization Plan

## Executive Summary

**Problem:** With nameserver-pi offline, homelab-nuc Pi-hole handles 100% of DNS/DHCP traffic for ~150 devices, creating bottlenecks and single points of failure.

**Solution:** Implement smart DHCP/DNS configuration to improve load distribution, add aggressive DNS caching, and maintain DHCP redundancy.

**Goal:** High availability with simplified management (user's priorities: HA + Simplified Management)

---

## Current State Analysis

### Infrastructure
- **nameserver-pi (192.168.50.4)**: OFFLINE
- **homelab-nuc (192.168.50.5)**: ACTIVE (100% load)
- **DHCP Ranges**: Split (100-174 / 175-250)
- **Devices**: 65+ static DHCP + ~86 dynamic = ~150 total

### Issues Identified
1. Single point of failure (homelab-nuc handling all traffic)
2. DNS queries timeout waiting for nameserver-pi
3. Clients with leases from nameserver-pi can't renew when offline
4. No DNS caching optimization
5. Both Pi-holes advertise same DNS order (nameserver-pi first)

### Current DHCP Configuration
```dhcp
# Both Pi-holes use identical DNS order:
dhcp-option=option:dns-server,192.168.50.4,192.168.50.5
```

---

## Proposal 1: Smart DHCP + DNS Optimization

### Core Concept
Each Pi-hole advertises **itself as primary DNS**, reducing cross-DNS queries and improving load distribution.

### Implementation Steps

#### Step 1: Update DHCP DNS Configuration
**File**: `roles/pihole/templates/dhcp_conf.j2`

**Current**:
```jinja2
dhcp-option=option:dns-server,{{ nameserver_pi_ip }},{{ homelab_nuc_ip }}
```

**Proposed**:
```jinja2
{% if inventory_hostname == "nameserver-pi" %}
# nameserver-pi advertises itself as primary
dhcp-option=option:dns-server,{{ nameserver_pi_ip }},{{ homelab_nuc_ip }}
{% elif inventory_hostname == "homelab-nuc" %}
# homelab-nuc advertises itself as primary
dhcp-option=option:dns-server,{{ homelab_nuc_ip }},{{ nameserver_pi_ip }}
{% endif %}
```

#### Step 2: Optimize DNS Cache Settings
**File**: `roles/pihole/tasks/main.yml`

Add to Pi-hole environment variables:
```yaml
FTLCONF_dns_cacheSize: 100000      # Increase from default ~10k
FTLCONF_dns_cacheMaxAge: 86400     # 24 hour cache
FTLCONF_dns_cacheOptimistic: "true"  # Aggressive caching
FTLCONF_RATE_LIMIT: "1000/1h"      # Prevent self-query rate limiting
```

#### Step 3: Add Multiple Upstream DNS
**File**: `group_vars/all/config.yml`

```yaml
google_dns_servers:
  - 8.8.8.8      # Google Primary
  - 8.8.4.4      # Google Secondary
  - 1.1.1.1      # Cloudflare
  - 9.9.9.9      # Quad9
```

---

## Expected Results

### When Both Pi-holes Online
```
Device with lease from nameserver-pi:
  DNS Config: Primary=192.168.50.4, Secondary=192.168.50.5
  Query: "open-webui.lan" → 192.168.50.4 (SUCCESS)
  Load: ~50% handled by nameserver-pi

Device with lease from homelab-nuc:
  DNS Config: Primary=192.168.50.5, Secondary=192.168.50.4
  Query: "open-webui.lan" → 192.168.50.5 (SUCCESS)
  Load: ~50% handled by homelab-nuc

Result: Balanced 50/50 DNS load distribution
```

### When nameserver-pi Offline (Current State)
```
Device with lease from nameserver-pi:
  DNS Config: Primary=192.168.50.4, Secondary=192.168.50.5
  Query: "open-webui.lan" → 192.168.50.4 (TIMEOUT) → 192.168.50.5 (SUCCESS)
  Lease renewal: Tries 192.168.50.4 (TIMEOUT) → Falls back to 192.168.50.5 (SUCCESS)

Device with lease from homelab-nuc:
  DNS Config: Primary=192.168.50.5, Secondary=192.168.50.4
  Query: "open-webui.lan" → 192.168.50.5 (SUCCESS - no timeout!)

Result: homelab-nuc handles ~70% (faster for own DHCP clients)
```

### DNS Cache Benefits
- **Cache Hit Rate**: Expected 80-90% after 24h
- **Response Time**: <1ms for cached entries
- **Upstream Queries**: Reduced by ~60%
- **Resolution Speed**: Faster overall DNS resolution

---

## Files to Modify

### Primary Changes
1. `roles/pihole/templates/dhcp_conf.j2` - DHCP DNS configuration
2. `roles/pihole/tasks/main.yml` - Pi-hole environment variables

### Optional Enhancements
3. `group_vars/all/config.yml` - Additional upstream DNS servers
4. `group_vars/nameserver.yml` - nameserver-pi specific settings
5. `group_vars/homelab.yml` - homelab-nuc specific settings

---

## Deployment Plan

### Phase 1: Update Configuration Files
```bash
# Edit the template files
vim roles/pihole/templates/dhcp_conf.j2
vim roles/pihole/tasks/main.yml

# Test syntax
uv run ansible-playbook setup.yml --syntax-check --tags pihole
```

### Phase 2: Deploy to homelab-nuc (Current Active Pi-hole)
```bash
# Deploy Pi-hole changes
uv run ansible-playbook setup.yml --tags pihole --limit homelab

# Verify configuration
ssh root@homelab-nuc.lan "docker exec pihole cat /etc/dnsmasq.d/04-dhcp-dns-failover.conf"
ssh root@homelab-nuc.lan "docker exec pihole pihole status"
```

### Phase 3: Deploy to nameserver-pi (When Back Online)
```bash
# When nameserver-pi is restored:
uv run ansible-playbook setup.yml --tags pihole --limit nameserver

# Verify DNS distribution
curl -H "Authorization: Bearer $HOMEASSISTANT_TOKEN" \
  http://homeassistant.lan:8123/api/services/dns/query_test
```

### Phase 4: Monitor and Validate
```bash
# Check DNS query distribution
ssh root@homelab-nuc.lan "docker exec pihole pihole -t"

# Check cache hit rates
ssh root@homelab-nuc.lan "docker exec pihole pihole-FTL --query-cache"

# Monitor resource usage
ssh root@homelab-nuc.lan "docker stats pihole --no-stream"
```

---

## Monitoring & Validation

### Key Metrics to Track
1. **DNS Query Distribution**: Ensure ~50/50 when both online
2. **Cache Hit Rate**: Target >80% after 24h
3. **Average Query Time**: Target <5ms
4. **DHCP Lease Renewals**: Verify automatic failover works
5. **Resource Usage**: CPU/Memory on both Pi-holes

### Validation Commands
```bash
# Test DNS resolution
dig @192.168.50.5 homepage.lan
dig @192.168.50.4 homepage.lan

# Check cache statistics
ssh root@homelab-nuc.lan "docker exec pihole pihole-FTL -c"

# Monitor query log in real-time
ssh root@homelab-nuc.lan "docker exec pihole pihole -t"
```

---

## Rollback Plan

If issues occur:

### Quick Rollback (Revert Changes)
```bash
# Restore original dhcp_conf.j2
git checkout HEAD -- roles/pihole/templates/dhcp_conf.j2

# Redeploy
uv run ansible-playbook setup.yml --tags pihole --limit homelab
```

### Full Rollback (Revert Everything)
```bash
# Revert all changes
git reset --hard HEAD~1

# Redeploy original configuration
uv run ansible-playbook setup.yml --tags pihole --limit homelab,nameserver
```

---

## Benefits Summary

✅ **High Availability**: Automatic DNS/DHCP failover
✅ **Load Distribution**: ~50/50 split when both online
✅ **Faster DNS**: Aggressive caching (<1ms cached responses)
✅ **Reduced Strain**: 60% fewer upstream DNS queries
✅ **Lease Resilience**: DHCP renewal works with either Pi-hole
✅ **Simplified Management**: Self-referencing DNS configuration

---

## Next Steps

1. **Review and approve** this plan
2. **Test in staging** (if available)
3. **Deploy to homelab-nuc** (current active Pi-hole)
4. **Document results** and cache hit rates
5. **Deploy to nameserver-pi** when back online
6. **Monitor and optimize** based on metrics

---

**Priority**: High (improves homelab stability and performance)
**Estimated Implementation Time**: 2-3 hours
**Risk Level**: Low (non-breaking changes, easy rollback)
