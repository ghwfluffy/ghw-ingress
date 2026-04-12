#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import re
import sys
import time
from pathlib import Path
from typing import Any

import yaml


LETS_ENCRYPT_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class ConfigError(ValueError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render Traefik config from ingress YAML.")
    parser.add_argument("--config", default="/config/ingress.yml")
    parser.add_argument("--static-output", default="/generated/static/traefik.yml")
    parser.add_argument("--dynamic-output", default="/generated/dynamic/traefik.yml")
    parser.add_argument("--status-dir", default="/generated/status")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"missing config file: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc

    if raw is None:
        raise ConfigError("configuration file is empty")
    if not isinstance(raw, dict):
        raise ConfigError("top-level YAML value must be a mapping")
    return raw


def require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{label} must be a mapping")
    return value


def require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{label} must be true or false")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label} must be a non-empty string")
    return value.strip()


def require_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{label} must be an integer")
    return value


def normalize_route(route: Any, index: int) -> dict[str, Any]:
    if not isinstance(route, dict):
        raise ConfigError(f"routes[{index}] must be a mapping")

    name = require_string(route.get("name"), f"routes[{index}].name").lower()
    if not NAME_PATTERN.match(name):
        raise ConfigError(
            f"routes[{index}].name must match {NAME_PATTERN.pattern}"
        )

    host = require_string(route.get("host"), f"routes[{index}].host")
    raw_path_prefix = route.get("path_prefix", "/")
    if not isinstance(raw_path_prefix, str):
        raise ConfigError(f"routes[{index}].path_prefix must be a string")
    path_prefix = raw_path_prefix.strip() or "/"
    if not path_prefix.startswith("/"):
        raise ConfigError(f"routes[{index}].path_prefix must start with '/'")

    has_target = "target" in route
    has_targets = "targets" in route
    if has_target == has_targets:
        raise ConfigError(
            f"routes[{index}] must define exactly one of 'target' or 'targets'"
        )

    if has_target:
        targets = [require_string(route.get("target"), f"routes[{index}].target")]
    else:
        raw_targets = route.get("targets")
        if not isinstance(raw_targets, list) or not raw_targets:
            raise ConfigError(f"routes[{index}].targets must be a non-empty list")
        targets = [
            require_string(value, f"routes[{index}].targets[{target_index}]")
            for target_index, value in enumerate(raw_targets)
        ]

    if "strip_prefix" in route:
        strip_prefix = require_bool(route["strip_prefix"], f"routes[{index}].strip_prefix")
    else:
        strip_prefix = False

    if "pass_host_header" in route:
        pass_host_header = require_bool(
            route["pass_host_header"], f"routes[{index}].pass_host_header"
        )
    else:
        pass_host_header = True

    normalized = {
        "name": name,
        "host": host,
        "path_prefix": path_prefix,
        "targets": targets,
        "strip_prefix": strip_prefix,
        "pass_host_header": pass_host_header,
    }

    if "priority" in route:
        normalized["priority"] = require_int(
            route["priority"], f"routes[{index}].priority"
        )

    return normalized


def normalize_config(raw: dict[str, Any]) -> dict[str, Any]:
    version = raw.get("version", 1)
    if version != 1:
        raise ConfigError("only version 1 is supported")

    ingress = require_mapping(raw.get("ingress"), "ingress")
    acme = require_mapping(ingress.get("acme"), "ingress.acme")
    dashboard = require_mapping(
        copy.deepcopy(ingress.get("dashboard", {})), "ingress.dashboard"
    )

    normalized = {
        "version": 1,
        "ingress": {
            "log_level": require_string(ingress.get("log_level", "INFO"), "ingress.log_level"),
            "access_log": require_bool(ingress.get("access_log", True), "ingress.access_log"),
            "redirect_to_https": require_bool(
                ingress.get("redirect_to_https", True),
                "ingress.redirect_to_https",
            ),
            "acme": {
                "email": require_string(acme.get("email"), "ingress.acme.email"),
                "staging": require_bool(acme.get("staging", False), "ingress.acme.staging"),
                "storage_file": require_string(
                    acme.get("storage_file", "/var/lib/traefik/acme.json"),
                    "ingress.acme.storage_file",
                ),
            },
            "dashboard": {
                "enabled": require_bool(
                    dashboard.get("enabled", False), "ingress.dashboard.enabled"
                ),
                "host": (
                    require_string(dashboard["host"], "ingress.dashboard.host")
                    if "host" in dashboard and str(dashboard["host"]).strip()
                    else ""
                ),
            },
        },
    }

    if normalized["ingress"]["dashboard"]["enabled"] and not normalized["ingress"]["dashboard"]["host"]:
        raise ConfigError("ingress.dashboard.host is required when the dashboard is enabled")

    routes = raw.get("routes")
    if not isinstance(routes, list) or not routes:
        raise ConfigError("routes must be a non-empty list")

    normalized_routes = [normalize_route(route, index) for index, route in enumerate(routes)]
    route_names = [route["name"] for route in normalized_routes]
    if len(route_names) != len(set(route_names)):
        raise ConfigError("route names must be unique")

    normalized["routes"] = normalized_routes
    return normalized


def build_rule(host: str, path_prefix: str) -> str:
    if path_prefix == "/":
        return f"Host(`{host}`)"
    return f"Host(`{host}`) && PathPrefix(`{path_prefix}`)"


def build_static_config(config: dict[str, Any]) -> dict[str, Any]:
    ingress = config["ingress"]
    static = {
        "global": {
            "checkNewVersion": False,
            "sendAnonymousUsage": False,
        },
        "entryPoints": {
            "web": {
                "address": ":80",
            },
            "websecure": {
                "address": ":443",
            },
        },
        "api": {
            "dashboard": ingress["dashboard"]["enabled"],
            "insecure": False,
        },
        "ping": {},
        "providers": {
            "file": {
                "directory": "/etc/traefik/dynamic",
                "watch": True,
            }
        },
        "certificatesResolvers": {
            "letsencrypt": {
                "acme": {
                    "email": ingress["acme"]["email"],
                    "storage": ingress["acme"]["storage_file"],
                    "httpChallenge": {
                        "entryPoint": "web",
                    },
                }
            }
        },
        "log": {
            "level": ingress["log_level"],
        },
    }

    if ingress["access_log"]:
        static["accessLog"] = {}

    if ingress["redirect_to_https"]:
        static["entryPoints"]["web"]["http"] = {
            "redirections": {
                "entryPoint": {
                    "to": "websecure",
                    "scheme": "https",
                    "permanent": True,
                }
            }
        }

    if ingress["acme"]["staging"]:
        static["certificatesResolvers"]["letsencrypt"]["acme"]["caServer"] = LETS_ENCRYPT_STAGING

    return static


def add_http_router(
    routers: dict[str, Any],
    name: str,
    rule: str,
    service_name: str,
    middleware_names: list[str],
    priority: int | None,
) -> None:
    router: dict[str, Any] = {
        "rule": rule,
        "entryPoints": ["web"],
        "service": service_name,
    }
    if middleware_names:
        router["middlewares"] = middleware_names
    if priority is not None:
        router["priority"] = priority
    routers[name] = router


def build_dynamic_config(config: dict[str, Any]) -> dict[str, Any]:
    ingress = config["ingress"]
    routers: dict[str, Any] = {}
    services: dict[str, Any] = {}
    middlewares: dict[str, Any] = {}

    for route in config["routes"]:
        rule = build_rule(route["host"], route["path_prefix"])
        middleware_names: list[str] = []
        priority = route.get("priority")

        if route["strip_prefix"] and route["path_prefix"] != "/":
            middleware_name = f"{route['name']}-strip-prefix"
            middlewares[middleware_name] = {
                "stripPrefix": {
                    "prefixes": [route["path_prefix"]],
                }
            }
            middleware_names.append(middleware_name)

        services[route["name"]] = {
            "loadBalancer": {
                "passHostHeader": route["pass_host_header"],
                "servers": [{"url": target} for target in route["targets"]],
            }
        }

        secure_router_name = f"{route['name']}-https"
        secure_router: dict[str, Any] = {
            "rule": rule,
            "entryPoints": ["websecure"],
            "service": route["name"],
            "tls": {
                "certResolver": "letsencrypt",
            },
        }
        if middleware_names:
            secure_router["middlewares"] = middleware_names
        if priority is not None:
            secure_router["priority"] = priority
        routers[secure_router_name] = secure_router

        if not ingress["redirect_to_https"]:
            add_http_router(
                routers=routers,
                name=f"{route['name']}-http",
                rule=rule,
                service_name=route["name"],
                middleware_names=middleware_names,
                priority=priority,
            )

    if ingress["dashboard"]["enabled"]:
        routers["dashboard-https"] = {
            "rule": f"Host(`{ingress['dashboard']['host']}`)",
            "entryPoints": ["websecure"],
            "service": "api@internal",
            "tls": {
                "certResolver": "letsencrypt",
            },
        }
        if not ingress["redirect_to_https"]:
            add_http_router(
                routers=routers,
                name="dashboard-http",
                rule=f"Host(`{ingress['dashboard']['host']}`)",
                service_name="api@internal",
                middleware_names=[],
                priority=None,
            )

    dynamic = {
        "http": {
            "routers": routers,
            "services": services,
        }
    }
    if middlewares:
        dynamic["http"]["middlewares"] = middlewares
    return dynamic


def atomic_write(path: Path, content: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(content, handle, sort_keys=False)
    temporary_path.replace(path)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(content, encoding="utf-8")
    temporary_path.replace(path)


def clear_file(path: Path) -> None:
    if path.exists():
        path.unlink()


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_once(config_path: Path, static_output: Path, dynamic_output: Path) -> None:
    normalized = normalize_config(load_yaml(config_path))
    atomic_write(static_output, build_static_config(normalized))
    atomic_write(dynamic_output, build_dynamic_config(normalized))


def main() -> int:
    args = parse_args()
    config_path = Path(args.config)
    static_output = Path(args.static_output)
    dynamic_output = Path(args.dynamic_output)
    status_dir = Path(args.status_dir)
    healthy_path = status_dir / "healthy"
    error_path = status_dir / "last-error.txt"
    last_seen_hash: str | None = None

    while True:
        try:
            current_hash = hash_file(config_path)
        except FileNotFoundError:
            current_hash = "__missing__"

        if current_hash != last_seen_hash:
            try:
                render_once(config_path, static_output, dynamic_output)
                write_text(healthy_path, "ok\n")
                clear_file(error_path)
                print(f"rendered config from {config_path}", flush=True)
            except ConfigError as exc:
                clear_file(healthy_path)
                write_text(error_path, f"{exc}\n")
                print(f"render failed: {exc}", file=sys.stderr, flush=True)
                if args.once:
                    return 1
            last_seen_hash = current_hash

        if args.once:
            return 0

        time.sleep(args.poll_interval)


if __name__ == "__main__":
    sys.exit(main())
