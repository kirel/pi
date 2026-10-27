# Dozzle and DNS resilience — 2026-10-27

## Dozzle

AI Lab was reachable and its services were running, but `dozzle-agent` had an
empty `NetworkSettings.Networks` map. Its Compose network also had no members.
The internal RPC healthcheck passed despite the missing network endpoint, while
connections from the NUC to `192.168.50.10:7007` were refused.

Repaired without pulling an image or restarting Docker:

```sh
docker network connect dozzle-agent_default dozzle-agent
```

The role now explicitly reconciles membership (preserving other members) and
checks the published TCP port from the UI host. The two new tasks were executed
against ailab: both passed with `changed=0` after the repair. This does not
establish why Docker lost the endpoint, or continuously monitor future losses.
The existing UI/agent version difference was not changed.

## DNS with the Pi offline and WAN IPv4 unavailable

The Pi at `192.168.50.4` is intentionally offline for maintenance. NUC Pi-hole
continued answering internal records. External requests timed out because its
only configured upstreams were Google IPv4 addresses. WAN IPv4 was unavailable
through the ZTE/Aldi Talk connection, while IPv6 HTTPS worked from ailab.

The NUC itself could query Google DNS over IPv6, but the Pi-hole Docker network
has no IPv6 route. The router at `192.168.50.1` successfully answered external
DNS queries from inside the Pi-hole container. Added `server={{ router_ip }}`
as an additional upstream in the existing dnsmasq resilience configuration.
Clients still use Pi-hole and retain local records and filtering.

**Requirement:** the router must use ISP/public DNS, not forward queries back
to Pi-hole (which would create a forwarding loop). Recheck this if router DNS
settings change. This fallback restores DNS, not IPv4 connectivity itself.

Validated the rendered configuration with `pihole-FTL dnsmasq-test`, then restarted
only the NUC Pi-hole container. The handler now also restarts it: `reloaddns`
uses SIGHUP and does not reread dnsmasq configuration files.

After startup, queries against NUC Pi-hole returned:

- `ailab-ubuntu.lan A`: `192.168.50.10`, 1 ms.
- `www.wikipedia.org A`: successful external answer, 63 ms.
- `example.com AAAA`: successful IPv6 answers, 38 ms.

Four regression tests cover the network repair, remote port check, router DNS
fallback and configuration restart handler. No Pi deployment or changes to its
maintenance state were made. Existing unrelated worktree changes were excluded.
