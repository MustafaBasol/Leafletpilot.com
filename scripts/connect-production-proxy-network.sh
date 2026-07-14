#!/usr/bin/env sh
set -eu

APP_NETWORK="${LEAFLETPILOT_APP_NETWORK:-leafletpilot_app}"
PROXY_CONTAINER="${COOLIFY_PROXY_CONTAINER:-coolify-proxy}"

if ! docker network inspect "$APP_NETWORK" >/dev/null 2>&1; then
  echo "ERROR: Docker network not found: $APP_NETWORK" >&2
  exit 1
fi

if ! docker inspect "$PROXY_CONTAINER" >/dev/null 2>&1; then
  echo "ERROR: Proxy container not found: $PROXY_CONTAINER" >&2
  exit 1
fi

if docker inspect "$PROXY_CONTAINER" \
  --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' \
  | grep -Fxq "$APP_NETWORK"; then
  echo "$PROXY_CONTAINER is already connected to $APP_NETWORK."
  exit 0
fi

docker network connect "$APP_NETWORK" "$PROXY_CONTAINER"

echo "$PROXY_CONTAINER connected to $APP_NETWORK."
