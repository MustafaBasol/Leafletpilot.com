# Backend Implementation Phases

## Phase 5: Backend Scaffold

Goal: Create the FastAPI backend foundation.

Exact scope:

- Add backend app folder.
- Add FastAPI health endpoint.
- Add environment settings.
- Add local PostgreSQL connection configuration.
- Add basic test setup.

Excluded work:

- No product APIs.
- No migrations beyond connection proof if not needed.
- No Telegram.
- No frontend API integration.

Validation commands:

```bash
python -m pytest
python -m uvicorn app.main:app --reload
curl http://127.0.0.1:8000/health
```

Next step: Add database models and Alembic in Phase 6.

## Phase 6: Core Data Models And Migrations

Goal: Create the tenant-aware database foundation.

Exact scope:

- Add SQLAlchemy or SQLModel setup.
- Add Alembic.
- Create migrations for users, markets, market users, products, brands, categories, aliases, templates, campaigns, campaign items, files, messages, activity logs, export jobs, bot connections, conversations, matching suggestions.
- Seed one demo market and minimal templates if useful.

Excluded work:

- No production auth.
- No Telegram webhook.
- No export rendering.

Validation commands:

```bash
alembic upgrade head
python -m pytest
```

Next step: Build catalog APIs in Phase 7.

## Phase 7: Products, Categories, Brands APIs

Goal: Replace product catalog mock data with backend-ready APIs.

Exact scope:

- Product list/search/create/update.
- Category list/create/update.
- Brand list/create/update.
- Product aliases.
- Product image metadata records.
- Market scoping and role checks.

Excluded work:

- No bulk Excel import.
- No real image processing.
- No AI matching.

Validation commands:

```bash
python -m pytest
curl http://127.0.0.1:8000/api/v1/markets/{marketId}/products
```

Next step: Add campaign APIs in Phase 8.

## Phase 8: Campaign APIs

Goal: Persist campaigns and campaign items through the backend.

Exact scope:

- Campaign list/detail/create/update.
- Parse raw text into campaign items with simple parser.
- Campaign status transitions.
- Activity log writes.
- File/export job records as placeholders.

Excluded work:

- No Telegram.
- No real export rendering.
- No Excel/PDF parser.

Validation commands:

```bash
python -m pytest
curl -X POST http://127.0.0.1:8000/api/v1/markets/{marketId}/campaigns
```

Next step: Add product matching service in Phase 9.

## Phase 9: Product Matching Service

Goal: Resolve campaign items against the product catalog.

Exact scope:

- Normalization utility.
- Exact match.
- Alias match.
- Barcode match.
- Fuzzy candidate scoring.
- Matching suggestions.
- Manual match endpoint.
- Missing product resolution actions.

Excluded work:

- No AI provider.
- No model training.
- No automatic product creation without user/operator action.

Validation commands:

```bash
python -m pytest
curl -X POST http://127.0.0.1:8000/api/v1/markets/{marketId}/campaigns/{campaignId}/match
```

Next step: Add Telegram MVP integration in Phase 10.

## Phase 10: Telegram MVP Integration

Goal: Create campaigns from Telegram text messages.

Exact scope:

- Telegram bot connection config.
- Webhook endpoint.
- Incoming message persistence.
- Conversation state.
- Text list campaign creation.
- Approval callback handling.
- Basic outgoing messages.

Excluded work:

- No WhatsApp.
- No Excel/PDF parser beyond placeholder handling.
- No final export rendering if Phase 11 has not started.

Validation commands:

```bash
python -m pytest
curl -X POST http://127.0.0.1:8000/api/v1/webhooks/telegram/{connectionId}
```

Next step: Build preview/export job architecture in Phase 11.

## Phase 11: Preview And Export Job Architecture

Goal: Prepare reliable file generation and delivery.

Exact scope:

- Export job service.
- Campaign file records.
- Object storage upload/download helpers.
- Signed URL generation.
- Placeholder preview/final job flow.
- Optional simple internal worker.

Excluded work:

- No advanced Playwright rendering unless explicitly included.
- No CMYK/print production pipeline.
- No CDN.

Validation commands:

```bash
python -m pytest
curl -X POST http://127.0.0.1:8000/api/v1/markets/{marketId}/campaigns/{campaignId}/export-jobs
```

Next step: Connect frontend to backend in Phase 12.

## Phase 12: Frontend API Integration

Goal: Replace local mock state with backend APIs screen by screen.

Exact scope:

- Auth/me integration.
- Dashboard data.
- Campaign list/detail.
- Product catalog.
- Templates.
- Bot connection status.
- Settings read/update.

Excluded work:

- No redesign.
- No unrelated frontend refactors.
- No WhatsApp.

Validation commands:

```bash
npm.cmd run validate
npm.cmd run build
npm.cmd run smoke
python -m pytest
```

Next step: Deployment planning in Phase 13.

## Phase 13: Deployment Planning

Goal: Define production path after MVP backend and frontend integration work.

Exact scope:

- Hosting choice.
- PostgreSQL hosting.
- Object storage provider.
- Secret management.
- Logging and error monitoring.
- Backup and restore plan.
- Telegram webhook public URL.

Excluded work:

- No premature Kubernetes.
- No multi-region architecture.
- No billing unless the business decision is ready.

Validation commands:

```bash
python -m pytest
npm.cmd run build
```

Next step: Execute deployment setup as a separate implementation phase.
