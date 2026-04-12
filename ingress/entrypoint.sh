#!/usr/bin/env bash
set -euo pipefail

STATIC_CONFIG="/etc/traefik/generated/static/traefik.yml"
TRAEFIK_PID=""

wait_for_config() {
  while [[ ! -s "${STATIC_CONFIG}" ]]; do
    echo "waiting for rendered Traefik static config at ${STATIC_CONFIG}"
    sleep 1
  done
}

config_hash() {
  sha256sum "${STATIC_CONFIG}" | awk '{print $1}'
}

acme_storage_path() {
  awk '$1 == "storage:" { print $2; exit }' "${STATIC_CONFIG}"
}

ensure_acme_storage() {
  local storage_path
  storage_path="$(acme_storage_path)"

  if [[ -z "${storage_path}" ]]; then
    echo "unable to determine ACME storage path from ${STATIC_CONFIG}" >&2
    exit 1
  fi

  mkdir -p "$(dirname "${storage_path}")"
  touch "${storage_path}"
  chmod 600 "${storage_path}"
}

start_traefik() {
  echo "starting Traefik with ${STATIC_CONFIG}"
  ensure_acme_storage
  /usr/local/bin/traefik --configFile="${STATIC_CONFIG}" &
  TRAEFIK_PID=$!
}

stop_traefik() {
  if [[ -n "${TRAEFIK_PID}" ]] && kill -0 "${TRAEFIK_PID}" 2>/dev/null; then
    kill "${TRAEFIK_PID}" 2>/dev/null || true
    wait "${TRAEFIK_PID}" || true
  fi
}

shutdown() {
  stop_traefik
  exit 0
}

trap shutdown INT TERM

wait_for_config
last_hash="$(config_hash)"
start_traefik

while true; do
  sleep 2

  if [[ ! -s "${STATIC_CONFIG}" ]]; then
    echo "rendered static config disappeared; waiting for it to return"
    stop_traefik
    wait_for_config
    last_hash="$(config_hash)"
    start_traefik
    continue
  fi

  if [[ -n "${TRAEFIK_PID}" ]] && ! kill -0 "${TRAEFIK_PID}" 2>/dev/null; then
    wait "${TRAEFIK_PID}" || true
    echo "Traefik exited; restarting"
    last_hash="$(config_hash)"
    start_traefik
    continue
  fi

  current_hash="$(config_hash)"
  if [[ "${current_hash}" != "${last_hash}" ]]; then
    echo "static config changed; restarting Traefik"
    stop_traefik
    last_hash="${current_hash}"
    start_traefik
  fi
done
