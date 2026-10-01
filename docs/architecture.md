# Architecture

## Overview

The stack has two long-running services:

- `config-renderer`: watches `config/ingress.yml`, validates it, and renders Traefik configuration into `generated/static/traefik.yml` and `generated/dynamic/traefik.yml`.
- `ingress`: runs Traefik, persists ACME state in `data/traefik/acme.json`, and restarts Traefik only when the rendered static configuration changes.

## Why Traefik

Traefik was chosen over NGINX because ACME issuance and renewal are built into the proxy itself, which keeps this project smaller and avoids a separate ACME client sidecar.

## Configuration Flow

`config/ingress.yml` is the only user-maintained runtime configuration file.

1. The renderer polls `config/ingress.yml`.
2. On change, it validates the schema and rewrites the generated Traefik files atomically.
3. Traefik watches the dynamic configuration directory and applies route changes without a restart.
4. The wrapper entrypoint restarts Traefik when the rendered static configuration changes, which covers ACME and entrypoint-level changes.

## Request Flow

1. Requests enter Traefik on ports `80` and `443`.
2. HTTP requests are redirected to HTTPS when `ingress.redirect_to_https` is enabled.
3. HTTPS routers are generated from `routes`.
4. Path-specific routes win first; optional `primary: true` routes act as host-level fallbacks.
5. Each route forwards to one or more upstream URLs defined in the same YAML file.

Optional `tcp_routes` create dedicated TCP entrypoints and exact-SNI TLS
passthrough routers. The backend receives the original TLS handshake and owns
mutual TLS authentication. Listener changes update static configuration and
therefore restart Traefik through the existing wrapper. HTTP routing remains
unchanged. Validate this contract with `python -m unittest discover -s renderer
-p 'test_*.py'` (PyYAML must be installed).

## ACME Lifecycle

- Certificates are stored in `data/traefik/acme.json`.
- The resolver is configured once from `config/ingress.yml`.
- Certificates are requested when a TLS router is matched for its host.
- Renewal is handled by Traefik automatically as long as the container keeps its ACME storage volume.

## Networking Model

- The ingress exposes `80` and `443` on the host.
- `host.docker.internal` is mapped to the host gateway, so routes can point at services running directly on the host.
- The Compose project creates a shared network named `ingress_proxy`. Other Docker Compose projects can join that network and be targeted by container DNS name.
