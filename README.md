# LeafletPilot

LeafletPilot is a FastAPI and React/Vite operator application for creating
market campaign brochures from structured catalog and campaign data.

## Production Baseline

Phase 19A adds a deployment baseline for a Linux VPS without performing a real
deployment:

- production settings validation
- backend and frontend production Docker images
- `docker-compose.production.yml` with private PostgreSQL and persistent export
  storage
- optional Traefik reverse-proxy example
- controlled Alembic migration workflow
- first-admin bootstrap script
- database and storage backup scripts
- validation-only GitHub Actions workflow

Start with
[docs/deployment/PRODUCTION_DEPLOYMENT.md](docs/deployment/PRODUCTION_DEPLOYMENT.md).

Current production limitations remain: access tokens are stored in
`localStorage`, refresh tokens/password reset/MFA/invitation email are not
implemented, storage is local mounted storage only, and there is no centralized
monitoring stack.
