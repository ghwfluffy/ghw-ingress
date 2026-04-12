# Website Ingress

This repository is a Docker Compose ingress built around Traefik. It terminates TLS with ACME, forwards traffic to multiple backend projects, and keeps all user-editable runtime configuration in a single YAML file: `config/ingress.yml`.

## What It Does

- Provisions and renews Let's Encrypt certificates automatically.
- Routes multiple hosts and path prefixes to different backend services.
- Supports a host-level fallback route for requests that do not match any explicit path prefix.
- Watches the mounted YAML config and applies changes automatically.
- Persists ACME state across restarts.

## Stack Layout

- `config/ingress.yml`: single source of truth for ingress settings and routes.
- `config-renderer`: validates the YAML and renders Traefik config into `generated/`.
- `ingress`: runs Traefik and restarts it automatically when static config changes.
- `data/traefik/acme.json`: persisted ACME account and certificate state.

## Quick Start

1. Edit `config/ingress.yml`.
2. Replace the example hosts and ACME email with real values.
3. Set `ingress.acme.staging: false` before production issuance.
4. Start the stack:

```bash
docker compose up -d --build
```

## Backend Targeting

Use backend URLs in `config/ingress.yml`:

- Host services: `http://host.docker.internal:3000`
- Services on the shared Docker network: `http://service-name:8080`

The Compose project creates a network named `ingress_proxy`. Other Docker Compose projects can join that network and be addressed by container name.

## Fallback Routing

Set `primary: true` on a route to make it the fallback backend for a host. That route will catch requests for the host that do not match any more specific `path_prefix` route on the same host.

## Config Reload Behavior

- Route changes are rendered into Traefik dynamic config and applied automatically.
- Changes that affect static proxy settings are rendered and then picked up by the ingress wrapper, which restarts Traefik automatically.
- If the YAML becomes invalid, the last known good rendered config remains in place.

## Documentation

- Architecture: `docs/architecture.md`
- Configuration schema: `docs/configuration.md`
- Agent guidance: `AGENTS.md`
