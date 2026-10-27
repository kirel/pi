# Pi-hole failover while nameserver-pi is offline

## Incident

With the Raspberry Pi (192.168.50.4) offline for maintenance, T3 Code was healthy
on ailab-ubuntu:8093, including requests from the NUC, but Caddy returned 502:
`dial tcp: lookup ailab-ubuntu.lan: i/o timeout`.

Caddy's container listed the Pi before the NUC (192.168.50.5). Go's default DNS
query timeout is 5 seconds, exceeding Caddy's default upstream dial deadline of
3 seconds. Merely listing two DNS servers did not allow timely fallback.

## Persistent fix

`roles/caddy/tasks/main.yml` now prefers the co-located NUC Pi-hole and retains
the Pi as a fallback. Docker `dns_opt` sets `timeout:1` and `attempts:2` so an
unresponsive first resolver does not consume the whole upstream dial deadline.
No public resolver is substituted for internal DNS. Deploy with:

```sh
uv run ansible-playbook setup.yml --tags caddy --limit homelab
```

## Verification

- Deployment completed: 22 OK, 1 changed, 0 failed/unreachable.
- NUC Pi-hole answers T3 DNS over both UDP and TCP, returning the CNAME to
  homelab-nuc.lan and A record 192.168.50.5. AAAA query for ailab-ubuntu.lan
  returns NOERROR with no answer, rather than timing out.
- NUC DHCP is active with its independent pool 192.168.50.175–250; its normal
  DHCP DNS option advertises both 192.168.50.4 and 192.168.50.5.
- T3 HTTPS returns 200 with the Pi offline.
- Fault test temporarily put the offline Pi FIRST in Caddy's live resolv.conf,
  retaining the new timeout options. After waiting for Go's 5-second resolver
  configuration refresh interval and forcing a Caddy reload to discard old
  upstream connection pools, a fresh HTTPS request returned 200 in 1.087 s.
- Restored the deployed NUC-first configuration and repeated the fresh-pool
  test: HTTPS 200 in 0.085 s. A shell EXIT trap protected resolver restoration.
- `uv run python -m unittest discover -s tests -p test_caddy_dns_failover.py -v`:
  both regression tests passed.

The phone itself has not been inspected. Clients must use the advertised local
DNS servers; manually pinned Pi-only DNS or browser DoH will not be repaired by
this server-side change. Reconnecting Wi-Fi refreshes client network state.
This validates Caddy and NUC DNS/DHCP configuration, not every application's
resolver implementation or a new DHCP lease on the phone. The reverse failure
scenario (NUC offline) cannot preserve NUC-hosted Caddy/services, even though the
Pi can still provide DNS/DHCP when it returns.
