# Configuration

All runtime configuration lives in `config/ingress.yml`.

## Top-Level Keys

### `version`

Schema version. This project currently supports `1`.

### `ingress`

Global ingress settings.

Supported keys:

- `log_level`: Traefik log level, such as `INFO` or `DEBUG`.
- `access_log`: enables Traefik access logs when `true`.
- `redirect_to_https`: redirects HTTP to HTTPS when `true`.
- `acme.email`: required email used for ACME account registration.
- `acme.staging`: when `true`, uses the Let's Encrypt staging directory.
- `acme.storage_file`: path inside the ingress container for ACME state. The default is `/var/lib/traefik/acme.json`.
- `dashboard.enabled`: enables the Traefik dashboard route.
- `dashboard.host`: hostname used for the dashboard when enabled.

### `routes`

List of routed backends.

Supported keys per route:

- `name`: required unique identifier.
- `host`: required hostname matched by the route.
- `path_prefix`: optional path prefix. Use `/` for the entire host.
- `primary`: when `true`, this route becomes the fallback for unmatched traffic on its host.
- `target`: a single upstream URL.
- `targets`: multiple upstream URLs for simple load balancing.
- `strip_prefix`: removes `path_prefix` before forwarding when `true`.
- `pass_host_header`: forwards the original `Host` header when `true`. Defaults to `true`.
- `priority`: optional Traefik router priority.

### `tcp_routes`

Optional list of dedicated TLS passthrough listeners. Each entry requires
`name`, `port`, `server_name` (an exact DNS hostname), and `target`
(`hostname:port`). Names must be unique across HTTP and TCP routes; ports must
be unique and cannot use 80 or 443. Publish the matching listener port in the
deployment compose file. Traefik uses `HostSNI` and passes the complete TLS
handshake to the backend, so the backend owns client-certificate verification.
These listeners never use the HTTP certificate resolver or HTTP middleware.

```yaml
tcp_routes:
  - name: devices
    port: 9443
    server_name: example.com
    target: device-api:9443
```

Each route must define exactly one of `target` or `targets`.

Fallback route rules:

- At most one `primary: true` route is allowed per host.
- A `primary: true` route matches the host without any path constraint.
- If a host has a `primary: true` route, that same host cannot also define a non-fallback `path_prefix: /` route.
- `strip_prefix` cannot be used on a `primary: true` route.

## Example

```yaml
version: 1

ingress:
  log_level: INFO
  access_log: true
  redirect_to_https: true
  acme:
    email: ops@example.com
    staging: false
    storage_file: /var/lib/traefik/acme.json
  dashboard:
    enabled: true
    host: traefik.example.com

routes:
  - name: site
    host: www.example.com
    primary: true
    target: http://host.docker.internal:3000

  - name: api
    host: www.example.com
    path_prefix: /api
    strip_prefix: true
    target: http://host.docker.internal:8080

  - name: ui
    host: www.example.com
    path_prefix: /app
    strip_prefix: true
    targets:
      - http://app-a:3000
      - http://app-b:3000
```

## Reload Behavior

- Route-only changes are applied without restarting Traefik.
- Changes that affect Traefik static configuration are rendered and then picked up by the wrapper process, which restarts Traefik automatically.
- Invalid YAML leaves the last known good rendered configuration in place and marks the renderer unhealthy.
