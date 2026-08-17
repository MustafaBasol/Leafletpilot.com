# Backend Implementation Phases

## Phase 18D: Roles, Market Switching, Team Members, Invitations

Implemented:

- Central market role constants and role dependencies.
- `market_admin`, `market_staff`, and `viewer` permission matrix.
- Role enforcement on campaign, catalog, template, export, member, and
  invitation routes.
- Market member list and role update endpoints.
- Invitation model, migration, creation, listing, revocation, public new-user
  acceptance, and authenticated existing-user acceptance.
- Seeded admin, staff, viewer, and a second demo market for admin switching.

Deferred:

- Member removal, automated invitation email, refresh tokens, password reset,
  MFA, production audit trail, and production deployment hardening.

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

## Phase 15: Real API Consistency And Minimal Templates

Goal: Harden Phase 14 real API flows and remove the template selection blocker
without adding a rendering engine.

Implemented scope:

- Campaign list/detail mapping uses backend count fields, Turkish labels, and
  resolved `template_name` when available.
- Campaign export-job/file placeholder statuses are displayed with Turkish UI
  labels.
- Missing `VITE_DEMO_MARKET_ID`, backend validation errors, and network errors
  remain visible as inline screen errors.
- Minimal `Template` model/API was added with global/market visibility.
- Seed data creates `Premium Market` and `Compact Weekly`.
- New Campaign can load templates and send `template_id` during text campaign
  creation.

Excluded work:

- No Telegram or WhatsApp.
- No AI parsing, OCR, Excel/PDF import, or real template rendering.
- No PDF/PNG generation, S3, deployment, payments, or full auth.

Validation commands:

```bash
python -m pytest -q
python -m alembic heads
python -m alembic upgrade head
python scripts/seed_dev_data.py
npm.cmd run validate
npm.cmd run build
npm.cmd run smoke
```

Next step: Phase 16 should plan preview/export architecture with
template-driven HTML/CSS and no S3 yet, then continue toward Telegram MVP
planning.

## Phase 16: Deterministic HTML Preview

Goal: Render real campaign preview HTML without generating files.

Implemented scope:

- `GET /api/campaigns/{campaign_id}/preview-html`.
- Deterministic template-backed HTML renderer.
- Sandboxed frontend iframe preview in real API mode.
- Preview renderer escaping tests.

Excluded work:

- No PDF/PNG generation.
- No S3/R2 storage.
- No background worker.
- No Telegram or WhatsApp.

## Phase 17: Local PDF/PNG Export Generation

Goal: Turn deterministic HTML preview into real local files.

Implemented scope:

- Playwright-based PDF and PNG generation.
- `LOCAL_STORAGE_DIR` local filesystem storage.
- Safe storage keys under
  `markets/{market_id}/campaigns/{campaign_id}/exports/{export_job_id}/...`.
- Synchronous `POST /api/campaigns/{campaign_id}/export-jobs`.
- `CampaignFile` rows for generated `brochure_pdf` and `brochure_png` files.
- Protected `GET /api/campaigns/{campaign_id}/files/{file_id}/download`.
- Campaign Detail real API controls to generate PDF, PNG, or both and download
  generated files.

Excluded work:

- No S3/R2/cloud storage.
- No Celery/RQ/Redis worker.
- No Telegram or WhatsApp.
- No auth/tenancy beyond `X-Market-Id`.
- No OCR, Excel/PDF import, AI parsing, or visual template editor.

Validation commands:

```bash
python -m pytest -q
python -m alembic heads
python -m alembic upgrade head
python scripts/seed_dev_data.py
npm.cmd run validate
npm.cmd run build
npm.cmd run smoke
```

Required local renderer setup:

```powershell
.\.venv\Scripts\python -m playwright install chromium
```

Next step: Phase 18B should focus on operational hardening before live use:
destructive action confirmations, visible real API errors, CORS/security
headers, and simple input/export guardrails. Full auth/tenancy should follow
before external customer access.

## Phase 18A: Customer-Facing Brochure Output

Implemented scope:

- Campaign preview/export renderer hides internal match badges and raw technical
  timestamps.
- EUR prices render in customer-facing format such as `1,59€`.
- Old prices use strikethrough styling.
- Premium Market and Compact Weekly layouts are improved for demo brochures.
- Campaign Detail can generate and download local PDF/PNG files.

Excluded work:

- No Telegram or WhatsApp.
- No auth/tenancy beyond `X-Market-Id`.
- No cloud storage, payments, deployment, AI parsing, OCR, or imports.

## Phase 18B: Operational Hardening

Implemented scope:

- Reusable frontend confirmation dialog for risky actions.
- Product active/passive, campaign item removal, missing-product removal, and
  template active/passive actions ask for confirmation.
- Real API mode shows inline API errors instead of silently replacing failed
  backend data with mock data.
- Shared API errors surface backend validation details, network failures, and
  missing `VITE_DEMO_MARKET_ID` clearly.
- Backend rejects wildcard CORS origins while credentials are enabled and keeps
  local Vite origins working.
- Backend adds `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  and basic `Permissions-Policy` headers.
- `parse-text` and `from-text` cap `raw_text` at 20,000 characters.
- Export jobs accept only `pdf`/`png` and at most two requested formats.

Excluded work:

- No Telegram or WhatsApp.
- No full auth, real tenancy, or role authorization.
- No AI parsing, OCR, Excel/PDF import, S3/R2/cloud storage, payments,
  deployment, React Query, state management library, or visual template editor.

Validation commands:

```bash
python -m pytest -q
python -m alembic heads
python -m alembic upgrade head
python scripts/seed_dev_data.py
npm.cmd run validate
npm.cmd run build
npm.cmd run smoke
```

Next step: Phase 18C or Phase 19 should start minimal auth/tenancy and role
authorization. Telegram MVP should come after that foundation, or only behind a
clear internal-only deployment boundary.

## Phase 18C: Minimal Auth And Market Tenancy Foundation

Implemented scope:

- Local MVP email/password login at `POST /api/auth/login`.
- Bearer access token and `GET /api/auth/me`.
- Seeded demo user `demo@leafletpilot.com` with local-only password `demo1234`.
- Token-based current user resolution.
- Membership-checked selected market access using `X-Market-Id`.
- `/api/catalog/*`, `/api/campaigns/*`, `/api/templates/*`, preview, export,
  and download routes require authentication and market membership.
- Frontend real API mode stores the token and first returned market, sends
  `Authorization` plus `X-Market-Id`, validates `/auth/me` on app load, and
  clears invalid sessions.

Excluded work:

- No Telegram or WhatsApp.
- No S3/R2/cloud storage.
- No payments or deployment.
- No OAuth or external auth provider.
- No refresh tokens, password reset, invitation flow, or full role matrix.
- No AI parsing, OCR, Excel/PDF import, or visual template editor.

Validation commands:

```bash
python -m pytest -q
python -m alembic heads
python -m alembic upgrade head
python scripts/seed_dev_data.py
npm.cmd run validate
npm.cmd run build
npm.cmd run smoke
```

Next step: Phase 18D should add role permissions, a market switcher, and user
invitation/onboarding. Phase 19 can start Telegram MVP after this foundation is
stable and deployment boundaries are clear.

## Phase 19A: Production Deployment Baseline

Implemented scope:

- Production settings validation rejects unsafe `ENVIRONMENT=production`
  configuration, including `DEBUG=true`, wildcard CORS, missing database URL,
  short or placeholder JWT secrets, and non-HTTPS `FRONTEND_BASE_URL`.
- Optional trusted-host middleware is configured through `TRUSTED_HOSTS`.
- Backend production Dockerfile runs Uvicorn without reload as a non-root user
  and includes Playwright Chromium for PDF/PNG export rendering.
- Frontend multi-stage Dockerfile builds Vite with public
  `VITE_API_BASE_URL` and serves `dist/` through unprivileged Nginx.
- Nginx SPA config includes fallback routing, immutable asset caching,
  no-cache `index.html`, gzip, and baseline security headers.
- `docker-compose.production.yml` defines private PostgreSQL, backend,
  frontend, named database/export volumes, health checks, and a one-off
  migration profile.
- Optional Traefik labels live in
  `deploy/traefik/docker-compose.traefik.example.yml`.
- Development seed refuses production execution.
- `scripts/create_admin.py` creates the first production `market_admin` without
  demo data.
- Linux backup scripts cover PostgreSQL and local export storage.
- `docs/deployment/PRODUCTION_DEPLOYMENT.md` documents deployment, migration,
  bootstrap, backup, restore, update, and rollback procedures.
- Validation-only GitHub Actions runs backend, frontend, Alembic head, Compose,
  and Docker build checks without deployment.

Excluded work:

- No real VPS deployment.
- No Telegram or WhatsApp.
- No S3/R2/object storage.
- No refresh tokens, password reset, MFA, OAuth, payments, or subscriptions.
- No Kubernetes, Terraform, production registry publishing, or live database
  access.
- No centralized monitoring platform or automatic zero-downtime migration
  guarantee.

Next step: Phase 19B should implement the internal Telegram Bot MVP only after
this production baseline has been validated in a disposable production-like
stack.

## Phase 32: Central WhatsApp Channel (Evolution API)

One platform-owned WhatsApp number, one centrally managed Evolution API
instance, many markets. The channel is an authorized operator/control channel
for LeafletPilot *market users* — it is explicitly not a customer/consumer
messaging or broadcast system.

Implemented scope:

- Central Evolution connection is runtime environment configuration
  (`EVOLUTION_*`, `LEAFLETPILOT_WHATSAPP_NUMBER`, `WHATSAPP_*`), validated at
  startup by `Settings` in the same style as the Telegram and Stripe blocks.
  Credentials are never persisted, never returned by an API, and never reach
  the browser bundle; Platform Admin sees derived health/status only.
- `POST /api/webhooks/evolution/whatsapp` accepts Evolution deliveries,
  authenticated by a constant-time comparison against
  `EVOLUTION_WEBHOOK_SECRET` presented as `X-Evolution-Webhook-Token` (or
  `Authorization: Bearer`). Evolution does not sign its payloads, so a
  configured header token is the strongest control the deployed version
  supports; reverse-proxy source-IP restriction is documented as additional
  defence, never as the only check.
- `whatsapp_webhook_events` is the idempotency ledger, with the same
  processing-lease semantics as `telegram_updates`, so a redelivered
  `messages.upsert` cannot verify twice or generate a second campaign.
- Verification: LeafletPilot issues a cryptographically random `LP-XXXX-XXXX`
  code, stored only as a keyed HMAC digest, single-use, expiring (10 minutes
  by default), with resend cooldown, attempt limits and per-user rate limits.
  The user sends it from their own handset; the Evolution webhook sender —
  not the number typed into the UI — establishes the verified identity.
- `user_whatsapp_identities` carries three partial unique indexes (per phone,
  per JID, per user, all scoped to `status='verified'`) so one verified
  WhatsApp identity can never silently represent two LeafletPilot users, while
  a user may still act for N markets.
- Single-market users resolve automatically; multi-market users are prompted
  and select by number, validated against live memberships. Every command
  re-resolves `market_users`, so a removed membership, deactivated user or
  suspended market takes effect on the next message with no cache to
  invalidate.
- Brochure generation reuses the existing channel-independent services
  (`app.services.campaign`, `app.services.templates`,
  `app.services.product_image_resolution`). The externally visible step
  (final PDF/PNG delivery) requires an explicit `ONAYLA` bound to user,
  market, action and expiry.
- Market UI lives on the existing Ekip page (`WhatsAppTeamPanel`); Platform
  Admin gains a WhatsApp page with connection health, a connection test, and a
  searchable/filterable identity table with revoke.
- Rate limiting reuses the proven `signup_throttles` bucketed counter; the
  migration only widens its `key_type` CHECK constraint.

Excluded work (deliberate):

- No customer/consumer phone books, bulk messaging, or campaign broadcast.
- No per-market WhatsApp accounts — one central number by design.
- No WhatsApp flyer *edit* intents yet (the Telegram channel's
  `parse_flyer_edit_intent` is intentionally not imported, to avoid coupling
  the new channel to code scheduled for removal).
- Evolution API is not added to `docker-compose.production.yml`; it is an
  external dependency, with a reference stack in
  `deploy/evolution/docker-compose.evolution.example.yml`.

Telegram: unchanged. No Telegram implementation file, route, model, or record
is touched by this phase; Telegram shutdown remains a separate future task.

Setup and operations: `docs/backend/10_WHATSAPP_EVOLUTION_SETUP.md`.
