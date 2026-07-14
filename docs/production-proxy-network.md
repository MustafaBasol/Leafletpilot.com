# Production Proxy Network

LeafletPilot production services use the private Docker network:

- leafletpilot_app

The following services must remain only on this application network:

- backend
- frontend
- postgres

Do not connect backend or frontend to another Coolify application UUID network.

Shared networks may contain another service using the Docker DNS alias postgres.
Connecting the LeafletPilot backend to such a network can make postgres resolve to
the wrong PostgreSQL container and cause authentication failures.

The Coolify Traefik proxy must instead be connected to leafletpilot_app:

    ./scripts/connect-production-proxy-network.sh

This command is idempotent. Run it after the Compose application network exists and
before external production smoke tests.

## Required smoke tests

    curl -fsS https://api.leafletpilot.com/api/health/db
    curl -fsSI https://leafletpilot.com | head -1
    curl -fsSI https://www.leafletpilot.com | head -1

Expected results:

- API database health returns HTTP 200.
- Main frontend domain returns HTTP 200.
- WWW frontend domain returns HTTP 200 or the configured redirect.

## Network architecture

- backend, frontend, and postgres remain on leafletpilot_app.
- coolify-proxy is additionally connected to leafletpilot_app.
- LeafletPilot application containers must not join another application's Coolify UUID network.
- Traefik routes use traefik.docker.network=leafletpilot_app.
