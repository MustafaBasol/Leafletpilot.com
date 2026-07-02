# LeafletPilot Backend

FastAPI backend for LeafletPilot. Phase 6 adds the first tenant-aware SQLAlchemy
business models and Alembic migration for the core catalog foundation.

## Setup

From the `backend` folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e .[dev]
```

## Run The API

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

The health endpoint is available at:

```text
http://127.0.0.1:8000/api/health
```

## Run Tests

```powershell
.\.venv\Scripts\python -m pytest
```

The normal test suite does not require PostgreSQL. The optional live database
check skips automatically when `DATABASE_URL` is not configured or reachable.

## Database Configuration

Copy `.env.example` to `.env` and set `DATABASE_URL`:

```text
DATABASE_URL=postgresql+asyncpg://leafletpilot:leafletpilot@localhost:5432/leafletpilot
```

The scaffold uses SQLAlchemy 2.x async sessions with `asyncpg`. This keeps the
database dependency ready for future webhook and job endpoints without changing
the application session pattern later.

`GET /api/health/db` runs `SELECT 1` when `DATABASE_URL` is configured. If the
database is not configured or unreachable, it returns `503`.

## Data Models

The initial business data layer uses SQLAlchemy 2.x typed declarative mappings
with UUID primary keys and timezone-aware timestamps.

Current model groups:

- Accounts and tenancy: `User`, `Market`, `MarketUser`
- Catalog: `Brand`, `Category`, `Product`, `ProductAlias`, `ProductImage`
- Audit trail: `ActivityLog`

Catalog records support global rows with `market_id = null` and `is_global =
true`, plus market-specific rows with `market_id` set and `is_global = false`.
Product aliases and images are owned by products and can cascade when a product
is deleted. Business CRUD APIs are not implemented yet.

## Alembic

Run migrations from the `backend` folder after configuring `DATABASE_URL`:

```powershell
.\.venv\Scripts\python -m alembic upgrade head
```

Check the current database revision:

```powershell
.\.venv\Scripts\python -m alembic current
```

Create a new migration later, after importing any new models into
`app.models`, with:

```powershell
.\.venv\Scripts\python -m alembic revision --autogenerate -m "describe change"
```

Live migration validation requires a reachable PostgreSQL database and a
configured `DATABASE_URL`.

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `APP_NAME` | `LeafletPilot API` | API service name. |
| `ENVIRONMENT` | `development` | Runtime environment label. |
| `DEBUG` | `false` | FastAPI debug mode. |
| `API_PREFIX` | `/api` | Prefix for API routes. |
| `BACKEND_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated frontend origins. |
| `DATABASE_URL` | unset | PostgreSQL async SQLAlchemy URL. |
| `TEST_DATABASE_URL` | unset | Optional database URL for future integration tests. |
| `LOG_LEVEL` | `INFO` | Python logging level. |

## Current Limitations

- No product, brand, category, alias, image, or activity CRUD APIs yet.
- No campaign workflow, bot, AI, PDF, storage, auth, payment, or deployment features.
- No seed data in the initial migration.
- The frontend remains mock/local-state only.

## Next Phase

Phase 7 should add Pydantic schemas and CRUD routes for products, brands, and
categories, with basic filtering/search, a market-scoping dependency placeholder,
and catalog API tests. Frontend API wiring should remain out of scope.
