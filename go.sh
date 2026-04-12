#!/bin/bash

set -eux -o pipefail

docker compose down -t0
docker compose up -d
docker compose logs -f
