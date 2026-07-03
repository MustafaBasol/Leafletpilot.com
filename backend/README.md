# LeafletPilot Backend

FastAPI backend for LeafletPilot. Phase 8 adds the campaign workflow data layer
on top of the catalog APIs from Phase 7.

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

## Catalog APIs

Catalog routes are mounted under `/api/catalog`:

- `GET|POST /api/catalog/brands`
- `GET|PATCH|DELETE /api/catalog/brands/{brand_id}`
- `GET|POST /api/catalog/categories`
- `GET|PATCH|DELETE /api/catalog/categories/{category_id}`
- `GET|POST /api/catalog/products`
- `GET|PATCH|DELETE /api/catalog/products/{product_id}`
- `POST /api/catalog/products/{product_id}/aliases`
- `DELETE /api/catalog/products/{product_id}/aliases/{alias_id}`

List routes return:

```json
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}
```

Brands, categories, and products support global rows and market-specific rows.
Use `include_global=true` on list routes to include global catalog entries
beside market-specific records.

Supported list filters:

- Brands: `search`, `is_active`, `is_global`, `include_global`, `limit`, `offset`
- Categories: `search`, `parent_id`, `is_active`, `is_global`, `include_global`, `limit`, `offset`
- Products: `search`, `brand_id`, `category_id`, `barcode`, `is_active`, `is_global`, `include_global`, `has_image`, `limit`, `offset`

Deletes are soft deletes and set `is_active=false`.

Product create accepts optional aliases and image metadata. Alias normalization
lowercases, trims, collapses whitespace, and removes common punctuation.
Turkish characters are preserved in normalized aliases for MVP matching
fidelity. Image metadata is stored only as database fields; there is no upload,
S3, or file storage workflow yet.

## Campaign Workflow Models

Phase 8 adds SQLAlchemy models and an Alembic migration for the campaign
workflow:

- `Campaign`: brochure generation workflow, status counters, source text, and selected template id.
- `CampaignItem`: parsed product lines with raw text, decimal-safe prices, optional product matches, and match state.
- `MatchingSuggestion`: candidate product matches with decimal-safe scores.
- `CampaignFile`: preview, source upload, and future final export file records.
- `ExportJob`: placeholder async job records for previews, final exports, regeneration, and file sending.
- `Conversation` and `IncomingMessage`: channel-independent conversation state and preserved raw provider payloads.

Campaign workflow statuses are stored as strings with database check
constraints:

```text
draft -> parsing -> matching -> missing_products -> preview_ready
preview_ready -> waiting_approval -> approved -> generating_files -> completed
revision_requested, failed, and cancelled are terminal or recovery states depending on later APIs.
```

All workflow records are scoped by `market_id` where appropriate. Campaign child
records cascade when their campaign is deleted; market deletion does not cascade
through workflow data. `Campaign.template_id` is a nullable UUID for now because
the `Template` model has not been implemented yet.

Campaign CRUD/list/detail APIs, item update APIs, matching resolution APIs, and
export job placeholder APIs are not implemented in Phase 8.

## Market Scoping Placeholder

There is no real authentication or tenancy resolution yet. Catalog routes use a
temporary header:

```text
X-Market-Id: <market uuid>
```

For market-specific create operations, `X-Market-Id` is required. Global create
operations use `is_global=true` and do not store a market id. Read/list/update
and soft-delete operations are scoped to global records plus the provided market
when the header is present. Without the header, catalog reads return only global
records.

This placeholder should be replaced by the real auth/tenancy dependency in a
future phase.

## Run Tests

```powershell
.\.venv\Scripts\python -m pytest
```

The normal test suite does not require PostgreSQL. The optional live database
check skips automatically when `DATABASE_URL` is not configured or reachable.

Catalog DB-backed CRUD tests also skip automatically unless
`TEST_DATABASE_URL` is configured. To run them against a local PostgreSQL test
database:

```powershell
$env:TEST_DATABASE_URL="postgresql+asyncpg://leafletpilot:leafletpilot@localhost:5432/leafletpilot_test"
.\.venv\Scripts\python -m pytest
```

The test creates missing tables with SQLAlchemy metadata. Use a disposable test
database, not a production or shared database.

Check Alembic heads without a database:

```powershell
.\.venv\Scripts\python -m alembic heads
```

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
- Campaign workflow: `Campaign`, `CampaignItem`, `MatchingSuggestion`, `CampaignFile`, `ExportJob`
- Messaging intake: `Conversation`, `IncomingMessage`
- Audit trail: `ActivityLog`

Catalog records support global rows with `market_id = null` and `is_global =
true`, plus market-specific rows with `market_id` set and `is_global = false`.
Product aliases and images are owned by products and can cascade when a product
is deleted. Catalog CRUD APIs are implemented for brands, categories, products,
and product aliases.

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

- Catalog APIs require `DATABASE_URL` for actual CRUD calls.
- Auth and market tenancy are represented only by the temporary `X-Market-Id` header.
- Product images accept metadata only; there is no upload or storage integration.
- Product alias normalization is intentionally simple and is not the matching engine.
- No activity CRUD APIs yet.
- Campaign workflow APIs are not implemented yet; Phase 8 only adds models, migration, metadata wiring, and tests.
- Campaign template references use a nullable UUID without a foreign key until the `Template` model is added.
- No bot integration, AI parsing, PDF/PNG rendering, S3 storage, auth, payment, or deployment features.
- No seed data in the initial migration.
- The frontend remains mock/local-state only.

## Next Phase

Phase 9 should focus on campaign Pydantic schemas, campaign CRUD/list/detail
APIs, campaign item update and matching resolution APIs, and export job
placeholder APIs. Telegram, AI parsing, and real PDF/PNG generation should stay
out of scope.
