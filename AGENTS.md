# Agent Notes

## Project Intent

This repository is a Docker Compose ingress built around Traefik. All user-editable runtime configuration lives in `config/ingress.yml`.

## Key Files

- `docker-compose.yml`: starts the renderer and ingress services.
- `config/ingress.yml`: the single source of truth for ACME and routing configuration.
- `renderer/render_config.py`: validates `config/ingress.yml` and renders Traefik static and dynamic config.
- `ingress/entrypoint.sh`: runs Traefik and restarts it when rendered static config changes.
- `docs/architecture.md`: component and reload design.
- `docs/configuration.md`: supported YAML schema and examples.
- `README.md`: high-level operator guide.

## Working Rules

- Keep all user-facing configuration in `config/ingress.yml`.
- Do not hand-edit files under `generated/`; they are runtime artifacts.
- Document architectural changes in `./docs/*.md`.
- Keep `README.md` current with high-level setup, operational behavior, and important constraints.
- Preserve bind-mounted volumes and auto-reload behavior when changing the stack.
