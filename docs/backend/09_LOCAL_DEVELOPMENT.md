# Local Backend Development

This guide sets up LeafletPilot backend development with PostgreSQL, Alembic
migrations, and repeatable demo data.

Run commands from the `backend` folder unless noted otherwise.

## Option A: Docker Desktop PostgreSQL

Start a local PostgreSQL 16 container:

```powershell
docker run --name leafletpilot-postgres `
  -e POSTGRES_USER=leafletpilot `
  -e POSTGRES_PASSWORD=leafletpilot `
  -e POSTGRES_DB=leafletpilot `
  -p 5432:5432 `
  -d postgres:16-alpine
```

Useful container commands:

```powershell
docker ps
docker logs leafletpilot-postgres
docker stop leafletpilot-postgres
docker start leafletpilot-postgres
docker rm -f leafletpilot-postgres
```

Create a separate test database if you want to run DB-backed tests:

```powershell
docker exec -it leafletpilot-postgres createdb -U leafletpilot leafletpilot_test
```

## Option B: Local PostgreSQL Install

Install PostgreSQL locally using the official installer or your preferred
package manager. Then:

1. Create a `leafletpilot` database user.
2. Create a `leafletpilot` development database owned by that user.
3. Optionally create a separate `leafletpilot_test` database for DB-backed tests.
4. Confirm PostgreSQL is listening on `localhost:5432`.

Use the same credentials shown below unless you intentionally choose different
local values.

## Environment

Create `backend/.env`:

```text
DATABASE_URL=postgresql+asyncpg://leafletpilot:leafletpilot@localhost:5432/leafletpilot
TEST_DATABASE_URL=postgresql+asyncpg://leafletpilot:leafletpilot@localhost:5432/leafletpilot_test_suite
```

`DATABASE_URL` is required for migrations, API CRUD calls, and seed data.
`TEST_DATABASE_URL` is optional; DB-backed tests skip when it is not configured.

## Install And Run

Install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e .[dev]
```

Apply migrations:

```powershell
.\.venv\Scripts\python -m alembic upgrade head
```

Seed demo data:

```powershell
.\.venv\Scripts\python scripts\seed_dev_data.py
```

Expected seed output includes:

```text
Demo market id: <market-id>
Demo user email: demo@leafletpilot.com
Rows created/updated/unchanged: <created>/<updated>/<unchanged>
Use the demo market id as X-Market-Id for market-scoped API calls.
```

Run the API:

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

Run tests:

```powershell
.\.venv\Scripts\python -m pytest
```

Check Alembic heads:

```powershell
.\.venv\Scripts\python -m alembic heads
```

## API Smoke Tests

Health:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

List products:

```powershell
Invoke-RestMethod -Headers @{ "X-Market-Id" = "<market-id>" } http://127.0.0.1:8000/api/catalog/products
```

Parse text:

```powershell
Invoke-RestMethod -Method Post `
  -ContentType "application/json" `
  -Body '{"raw_text":"Coca Cola 2L - 1.59€","default_currency":"EUR"}' `
  http://127.0.0.1:8000/api/campaigns/parse-text
```

Create campaign from text:

```powershell
Invoke-RestMethod -Method Post `
  -Headers @{ "X-Market-Id" = "<market-id>" } `
  -ContentType "application/json" `
  -Body '{"title":"Hafta 28 Kampanyası","raw_text":"Coca Cola 2L - 1.59€","generate_suggestions":true}' `
  http://127.0.0.1:8000/api/campaigns/from-text
```

## Seed Data

The seed script creates or updates:

- Demo user: `demo@leafletpilot.com`
- Demo market: `Anadolu Market`
- A `market_admin` membership for the demo user
- Global demo categories, brands, products, aliases, and image metadata
- One demo campaign from pasted text

The script is idempotent. Running it multiple times updates known rows and does
not create duplicate demo users, markets, catalog rows, aliases, image metadata,
or demo campaigns.

Limitations:

- No real files are created.
- Product image rows use placeholder URLs only.
- No upload, S3, PDF/PNG generation, AI parsing, Telegram, WhatsApp, payments,
  deployment, or real auth is configured by this guide.
