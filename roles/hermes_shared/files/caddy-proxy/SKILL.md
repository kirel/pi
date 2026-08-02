---
name: caddy-proxy
description: Publish a local HTTP service or static site under the HTTPS namespace assigned to this Hermes agent.
metadata:
  hermes:
    tags: [caddy, https, reverse-proxy, static-sites, local-services]
    category: devops
    requires_toolsets: [terminal]
---

# Caddy Proxy

Use this skill when the user asks to publish a local web app, API, dashboard,
report, preview, static page, or webhook under a friendly HTTPS URL.

The Ansible-managed `hermes-service` command is the only supported publishing
interface. Do not edit the managed Caddyfile, write Caddy snippets directly, or
handle DNS-provider credentials.

## Discover this agent's namespace

Always start with:

```bash
hermes-service info
```

It reports the runtime, URL namespace, reserved names, static publishing roots,
and service manager. The implementation differs between bare metal and Docker,
but the commands below are identical.

## Publish a local HTTP service

Bind the application to `127.0.0.1`, then publish its port:

```bash
hermes-service publish myapp 3456
hermes-service check myapp
```

The resulting URL is printed by the command. Use a lowercase DNS label made of
letters, digits, and hyphens. Do not use a name reported as reserved by `info`.

For anything that must survive a restart, use the service manager reported by
`info`: Supervisor in Docker or a systemd user service on bare metal. Do not
rely on a background shell process for a persistent service.

## Publish static files

```bash
hermes-service publish-static report /absolute/path/to/report
hermes-service check report
```

Static files are copied into the Caddy-specific serving directory. Run the
publish command again after changing the source files.

## Inspect or remove routes

```bash
hermes-service list
hermes-service remove myapp
```

## Security

- Published URLs use real HTTPS certificates obtained through DNS-01.
- They are intended to be reachable only through the Tailnet and its ACLs.
- HTTPS does not add application authentication. Discuss explicit auth before
  publishing personal data, write-capable APIs, or webhooks.
- Proxy only to a loopback service. Never bind an app to the VPS public address
  just to make publishing work.
- Never request, read, copy, or print the DNS-provider token.

## Troubleshooting

- `502`: the backend is stopped, uses a different port, or is not listening on
  `127.0.0.1`.
- `404`: no route exists for that service name, or static files are missing.
- A publish or removal error leaves the previous Caddy configuration active.
- Use `hermes-service check <name>` for the local TLS/SNI/backend check, then
  test the printed URL from a second Tailnet client when needed.
