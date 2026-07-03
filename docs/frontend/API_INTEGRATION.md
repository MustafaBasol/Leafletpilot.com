# Frontend API Integration

Phase 13 keeps the frontend in mock mode by default and adds an opt-in real API
mode for safe read-only integration work.

## Environment Variables

Create a frontend `.env.local` file when you want to use the backend:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000/api
VITE_USE_REAL_API=false
VITE_DEMO_MARKET_ID=
```

- `VITE_API_BASE_URL` points at the FastAPI API prefix.
- `VITE_USE_REAL_API=true` switches supported reads to backend calls.
- `VITE_DEMO_MARKET_ID` is sent as `X-Market-Id` for market-scoped requests.

## Run Backend

From `backend/`, set up PostgreSQL and dependencies using
`docs/backend/09_LOCAL_DEVELOPMENT.md`, then run:

```powershell
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python scripts\seed_dev_data.py
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

The seed command prints:

```text
Demo market id: <market-id>
```

Use that value as `VITE_DEMO_MARKET_ID`.

## Mock Mode

Mock mode is the default and does not require the backend:

```powershell
npm.cmd run dev
```

Either omit `.env.local` or keep:

```text
VITE_USE_REAL_API=false
```

Campaign and product screens continue using local demo data and local product
edit state.

## Real API Mode

With the backend running and seeded:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000/api
VITE_USE_REAL_API=true
VITE_DEMO_MARKET_ID=<market-id>
```

Restart Vite after changing env variables.

Currently wired read operations:

- Campaigns list calls `GET /api/campaigns`.
- Product Catalog initial list calls `GET /api/catalog/products`.
- Settings shows an API status panel and calls `GET /api/health`.

If a real API read fails, the page shows a friendly inline error and keeps the
mock data visible so the demo remains usable.

## Current Limitations

- Product create/edit/toggle actions remain local frontend state.
- Campaign detail still uses mock page data.
- New Campaign still uses the deterministic mock wizard data.
- Brand and category names are not expanded on product rows yet because current
  product responses expose `brand_id` and `category_id`.
- No auth token is sent; `X-Market-Id` is the temporary tenancy placeholder.
- No Telegram, WhatsApp, AI parsing, PDF/PNG generation, S3, payments,
  deployment, or real auth is implemented here.

## Phase 14 Plan

Phase 14 should run the backend with PostgreSQL and seed data, enable
`VITE_USE_REAL_API=true`, then finish wiring Campaigns and Product Catalog to
real API data. After that, wire New Campaign pasted text to
`POST /api/campaigns/from-text` and map the created campaign into the detail
workflow.

