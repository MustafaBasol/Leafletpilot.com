# LeafletPilot Backend

FastAPI backend for LeafletPilot. Phase 9 adds backend-only campaign workflow
APIs on top of the catalog APIs and campaign data layer from earlier phases.

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

## Campaign APIs

Campaign routes are mounted under `/api/campaigns` and require the temporary
market header:

```text
X-Market-Id: <market uuid>
```

If the header is missing, campaign routes return `400` before opening a
database session. This is a tenancy placeholder until real auth resolves the
active market.

Implemented campaign routes:

- `GET|POST /api/campaigns`
- `GET|PATCH|DELETE /api/campaigns/{campaign_id}`
- `POST /api/campaigns/{campaign_id}/items`
- `PATCH /api/campaigns/{campaign_id}/items/{item_id}`
- `POST /api/campaigns/{campaign_id}/items/{item_id}/resolve-match`
- `GET|POST /api/campaigns/{campaign_id}/items/{item_id}/suggestions`
- `GET|POST /api/campaigns/{campaign_id}/files`
- `GET|POST /api/campaigns/{campaign_id}/export-jobs`

List campaigns:

```powershell
curl.exe -H "X-Market-Id: <market uuid>" "http://127.0.0.1:8000/api/campaigns?status=draft&limit=50&offset=0"
```

List filters are `search`, `status`, `channel`, `source_type`, `date_from`,
`date_to`, `limit`, and `offset`. Results are ordered by `created_at`
descending and return the shared list envelope:

```json
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}
```

Create a campaign with manual items:

```json
{
  "title": "Hafta 28",
  "channel": "panel",
  "source_type": "manual",
  "raw_input_text": "Coca Cola 2L - 1.59",
  "currency": "EUR",
  "language": "tr",
  "items": [
    {
      "raw_line": "Coca Cola 2L - 1.59",
      "incoming_name": "Coca Cola 2L",
      "price": "1.59"
    }
  ]
}
```

Get campaign detail:

```powershell
curl.exe -H "X-Market-Id: <market uuid>" "http://127.0.0.1:8000/api/campaigns/<campaign uuid>"
```

Detail responses include campaign metadata, items, files, export jobs, and
matching suggestions. Money and score fields use Pydantic `Decimal`; JSON
responses serialize them as strings.

Resolve an item match manually:

```json
{
  "resolution": "manual_selected",
  "product_id": "<product uuid>",
  "display_name": "Coca Cola 2L",
  "notes": "Operator selected the catalog product."
}
```

Supported resolutions are `manual_selected`, `new_product_needed`,
`use_without_image`, `excluded`, and `not_found`. Manual selection requires a
product visible to the current market: either a market-specific product with
the same `market_id`, or an active global product.

Campaign counts are recalculated after item changes. `product_count` counts
non-excluded items. `matched_count` counts `matched` and `manual_selected`.
`missing_count` counts `not_found`, `new_product_needed`, and
`use_without_image`. `low_confidence_count` counts `low_confidence`.

Export jobs are placeholders only:

```json
{
  "job_type": "preview",
  "requested_formats": ["preview_png"],
  "status": "queued"
}
```

Creating an export job stores a queued `ExportJob` row. It does not start a
worker, generate files, upload to storage, or send messages. Campaign file
routes similarly store metadata only; there is no upload or generation path in
this phase.

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

Campaign CRUD/list/detail APIs, item update APIs, matching resolution APIs,
matching suggestion placeholder APIs, campaign file metadata APIs, and export
job placeholder APIs are implemented in Phase 9.

## Market Scoping Placeholder

There is no real authentication or tenancy resolution yet. Catalog routes use a
temporary header:

```text
X-Market-Id: <market uuid>
```

For catalog market-specific create operations, `X-Market-Id` is required.
Global catalog create operations use `is_global=true` and do not store a market
id. Catalog read/list/update and soft-delete operations are scoped to global
records plus the provided market when the header is present. Without the
header, catalog reads return only global records. Campaign routes always require
`X-Market-Id`.

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

- Catalog and campaign APIs require `DATABASE_URL` for actual CRUD calls.
- Auth and market tenancy are represented only by the temporary `X-Market-Id` header.
- Product images accept metadata only; there is no upload or storage integration.
- Product alias normalization is intentionally simple and is not the matching engine.
- Campaign item creation is manual only; there is no AI parsing.
- Matching suggestions can be stored as placeholder/demo data, but no matching engine exists yet.
- Campaign file and export job APIs store metadata only; no PDF/PNG generation or background worker runs.
- No activity CRUD APIs yet.
- Campaign template references use a nullable UUID without a foreign key until the `Template` model is added.
- No Telegram or WhatsApp integration, real matching, S3 storage, frontend API integration, payment, or deployment features.
- No seed data in the initial migration.
- The frontend remains mock/local-state only.

## Next Phase

Phase 10 should focus on a deterministic product matching service: exact,
alias, barcode, and fuzzy matching; suggestion generation; and a clear
interface where AI can be added later without enabling AI behavior yet.
