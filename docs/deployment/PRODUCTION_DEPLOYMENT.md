# LeafletPilot Production Deployment

This is a reproducible baseline for a Linux VPS deployment. It does not deploy
to a real server and does not include production credentials.

## Current Limits

- Access tokens are still stored in frontend `localStorage`.
- There are no refresh tokens, password reset, MFA, OAuth, or automated
  invitation emails.
- Export storage is local mounted storage only, with no S3/R2 replication.
- There is no centralized observability stack or automatic zero-downtime
  migration guarantee.

## Required Files

- `.env.production.example`
- `docker-compose.production.yml`
- `deploy/traefik/docker-compose.traefik.example.yml` when using Traefik
- `deploy/backup/*.sh`

## First Deployment

1. Install Docker Engine and the Docker Compose plugin on the VPS.
2. Clone the repository.
3. Copy `.env.production.example` to a private env file and fill every required
   blank. Never commit the private env file.
4. Generate `JWT_SECRET_KEY`:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(64))"
   ```

5. Configure DNS:
   - `APP_DOMAIN` points to the frontend host.
   - `API_DOMAIN` points to the backend API host.
6. Prepare an HTTPS reverse proxy. TLS must terminate at the proxy.
7. Set `BACKEND_CORS_ORIGINS` to exactly the frontend origin, for example
   `["https://app.example.com"]`.
8. Set `FRONTEND_BASE_URL=https://${APP_DOMAIN}`.
9. Set `VITE_API_BASE_URL=https://${API_DOMAIN}/api`. This value is public and
   embedded into the frontend image at build time.
10. Build images:

    ```bash
    docker compose --env-file .env.production -f docker-compose.production.yml build
    ```

11. Start PostgreSQL:

    ```bash
    docker compose --env-file .env.production -f docker-compose.production.yml up -d postgres
    ```

12. Verify PostgreSQL health:

    ```bash
    docker compose --env-file .env.production -f docker-compose.production.yml ps postgres
    ```

13. Check Alembic heads:

    ```bash
    docker compose --env-file .env.production -f docker-compose.production.yml run --rm migration python -m alembic heads
    ```

    There must be exactly one head.

14. Run migration:

    ```bash
    docker compose --env-file .env.production -f docker-compose.production.yml run --rm migration
    ```

15. Check the database revision:

    ```bash
    docker compose --env-file .env.production -f docker-compose.production.yml run --rm migration python -m alembic current
    ```

16. Create the first production admin. Prefer prompts so the password is not in
    shell history:

    ```bash
    docker compose --env-file .env.production -f docker-compose.production.yml run --rm backend python scripts/create_admin.py
    ```

    Environment variables are also supported: `ADMIN_EMAIL`, `ADMIN_FULL_NAME`,
    `ADMIN_MARKET_NAME`, and `ADMIN_PASSWORD`. Avoid passing passwords as
    command arguments.

17. Start backend and frontend:

    ```bash
    docker compose --env-file .env.production -f docker-compose.production.yml up -d backend frontend
    ```

18. Verify liveness and readiness:

    ```bash
    docker compose --env-file .env.production -f docker-compose.production.yml exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health').read().decode())"
    docker compose --env-file .env.production -f docker-compose.production.yml exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health/db').read().decode())"
    ```

19. Open `https://${APP_DOMAIN}` and log in as the created admin.
20. Generate a test brochure PDF and PNG.
21. Restart the backend and verify the exported file still downloads:

    ```bash
    docker compose --env-file .env.production -f docker-compose.production.yml restart backend
    ```

22. Configure backup cron for database and storage.
23. Run and verify one backup.
24. Record the active image tags and migration revision.

## Traefik Example

The base Compose file does not force Traefik. To use the example override:

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.production.yml \
  -f deploy/traefik/docker-compose.traefik.example.yml \
  up -d
```

Expected routing:

- `https://${APP_DOMAIN}` to `frontend:8080`
- `https://${API_DOMAIN}` to `backend:8000`

Uvicorn is started with `--proxy-headers`. Keep trusted proxy traffic limited to
the Docker network and set `TRUSTED_HOSTS` to the exact API host.

The frontend Nginx config sets baseline security headers but does not set a
Content-Security-Policy yet. Add CSP only after testing the same-origin preview
iframe, blob downloads, and API calls in the deployed browser environment.

## Storage

Production Compose mounts `leafletpilot_storage` at `/app/storage`.
`LOCAL_STORAGE_DIR` must be `/app/storage` inside the container. Generated
database rows store safe relative storage keys, not host paths.

If using a host bind mount instead of the named volume, ensure the backend
container user can write to it before starting the API.

Do not run `scripts/seed_dev_data.py` in production. No demo account should
exist in production.

## Backups

Install `pg_dump`, `sha256sum`, and `tar` on the backup runner.

Database backup:

```bash
POSTGRES_HOST=127.0.0.1 \
POSTGRES_DB=leafletpilot \
POSTGRES_USER=leafletpilot \
PGPASSWORD=... \
BACKUP_DIR=/path/to/backups \
deploy/backup/postgres_backup.sh
```

Storage backup:

```bash
STORAGE_DIR=/path/to/storage \
BACKUP_DIR=/path/to/backups \
deploy/backup/storage_backup.sh
```

Set `RETENTION_DAYS` to override the default `14`.

## Restore

Restores overwrite data. Take a maintenance window, stop backend writes, and
create a safety backup first. Database and storage backups should come from
approximately the same point in time.

Database restore into an empty or new database where possible:

```bash
sha256sum -c backup.dump.sha256
createdb leafletpilot_restore
pg_restore --dbname=leafletpilot_restore --no-owner backup.dump
python -m alembic current
```

Verify ownership, extensions, app login, and `/api/health/db` before promoting
the restored database.

Storage restore:

```bash
sha256sum -c leafletpilot_storage.tar.gz.sha256
systemctl stop backend-or-compose-service
tar -xzf leafletpilot_storage.tar.gz -C /restore/parent
chown -R <backend-user>:<backend-group> /restore/parent/storage
systemctl start backend-or-compose-service
```

Then test a protected file download.

Automatic Alembic downgrade is not provided. Database rollback requires an
explicit migration and backup plan.

## Update Flow

1. Pull code.
2. Review release notes and migrations.
3. Create database and storage backups.
4. Build new images.
5. Check Alembic heads.
6. Run `alembic upgrade head`.
7. Recreate backend and frontend.
8. Check `/api/health` and `/api/health/db`.
9. Log in, call the API, generate and download a PDF/PNG.
10. Retain the previous image tag for application rollback.

Application images may be rolled back. Database rollback is not automatically
safe; do not run `alembic downgrade` blindly.
