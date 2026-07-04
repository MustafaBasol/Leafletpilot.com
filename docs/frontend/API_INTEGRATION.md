# Frontend API Integration

Phase 15 keeps mock mode as the default and expands opt-in real API mode across
campaign creation/detail, core catalog management screens, and minimal template
selection.

## Environment Variables

Create a frontend `.env.local` file when you want to use the backend:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000/api
VITE_USE_REAL_API=false
VITE_DEMO_MARKET_ID=
```

- `VITE_API_BASE_URL` points at the FastAPI API prefix.
- `VITE_USE_REAL_API=true` switches supported screens to backend calls.
- `VITE_DEMO_MARKET_ID` is sent as `X-Market-Id` for market-scoped requests.

If real API mode is enabled without `VITE_DEMO_MARKET_ID`, supported screens show
a friendly inline error instead of crashing.

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

Mock mode does not require the backend:

```powershell
npm.cmd run dev
```

Either omit `.env.local` or keep:

```text
VITE_USE_REAL_API=false
```

Campaign, product, brand, category, and template screens continue using local
demo data or local UI state.

## Real API Mode

With the backend running and seeded:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000/api
VITE_USE_REAL_API=true
VITE_DEMO_MARKET_ID=<market-id>
```

Restart Vite after changing env variables.

Currently wired operations:

- Campaigns list calls `GET /api/campaigns`.
- Campaign Detail calls `GET /api/campaigns/{campaign_id}` and displays backend
  campaign metadata, item counts, campaign items, match status, suggestions,
  files, and export jobs when present.
- Campaign Detail can call:
  - `POST /api/campaigns/{campaign_id}/generate-suggestions`
  - `POST /api/campaigns/{campaign_id}/items/{item_id}/generate-suggestions`
  - `POST /api/campaigns/{campaign_id}/items/{item_id}/resolve-match`
  - `POST /api/campaigns/{campaign_id}/export-jobs`
- New Campaign pasted text Step 2 calls `POST /api/campaigns/parse-text` for a
  deterministic parser preview.
- New Campaign final create calls `POST /api/campaigns/from-text` with
  `channel=panel`, `source_type=text`, `generate_suggestions=true`, and
  `suggestion_limit=5`, then opens the created campaign detail route.
- Product Catalog calls `GET /api/catalog/products`, `GET /api/catalog/brands`,
  and `GET /api/catalog/categories`.
- Product Catalog maps `brand_id` and `category_id` to display names, and search
  plus brand/category/image/status filters run client-side on the loaded rows.
- Product Catalog create calls `POST /api/catalog/products`.
- Product Catalog edit calls `PATCH /api/catalog/products/{product_id}`.
- Product Catalog alias edits call `POST /api/catalog/products/{product_id}/aliases`
  and `DELETE /api/catalog/products/{product_id}/aliases/{alias_id}` as needed.
- Product Catalog active/passive toggle calls
  `PATCH /api/catalog/products/{product_id}` with `is_active`.
- Brands page calls `GET /api/catalog/brands` and can create with
  `POST /api/catalog/brands`.
- Categories page calls `GET /api/catalog/categories` and can create with
  `POST /api/catalog/categories`.
- Templates page calls `GET /api/templates`, displays global plus visible
  market templates, and can toggle active/passive state with
  `PATCH /api/templates/{template_id}`.
- Template Detail calls `GET /api/templates/{template_id}` in real API mode.
- New Campaign loads templates from `GET /api/templates` and sends the selected
  `template_id` to `POST /api/campaigns/from-text`.
- Campaign list/detail displays `template_name` when the backend can resolve the
  selected template. If only `template_id` exists, the UI shows a clear
  placeholder instead of inventing a name.
- Settings shows an API status panel and calls `GET /api/health`.

Backend validation errors are displayed inline with readable field messages when
the API returns structured validation details.

## Manual Real API Smoke Checklist

1. Run backend.
2. Run seed.
3. Set `.env.local` with `VITE_USE_REAL_API=true`,
   `VITE_API_BASE_URL=http://127.0.0.1:8000/api`, and the seeded
   `VITE_DEMO_MARKET_ID`.
4. Run frontend.
5. Check Settings health.
6. Check Campaigns.
7. Open Campaign Detail.
8. Generate suggestions from Campaign Detail.
9. Create New Campaign from pasted text.
10. Verify new campaign appears in list/detail.
11. Check Product Catalog search/filter/write actions.
12. Check Brands/Categories.
13. Check Templates list/detail.
14. Create a New Campaign with a selected template and verify the template name
    appears in Campaigns and Campaign Detail.

## Known Mock/Real Differences

- Mock template actions such as duplicate and default selection are local UI
  simulations. Real API mode persists active/passive status only.
- Mock campaign preview and generated files are illustrative. Real API mode
  stores export-job/file metadata placeholders but does not render files.
- Mock mode can create local product, brand, category, and template-like UI
  state without validation. Real API mode returns backend validation messages.

## Current Limitations

- No real auth; `X-Market-Id` is the temporary tenancy placeholder.
- No file generation.
- No S3 uploads or downloads.
- No Telegram or WhatsApp integration.
- No AI parsing; pasted text uses deterministic backend parsing.
- Minimal Template model/API exists for selection and visibility, but no real
  template rendering engine exists yet.
- Product image upload remains a placeholder.
- Campaign brochure preview frame remains placeholder UI.

## Recommended Phase 16

- Start preview/export architecture planning with template-driven HTML/CSS and
  placeholder storage boundaries, but no S3 yet.
- Keep Telegram MVP planning next after the preview/export architecture is clear.
