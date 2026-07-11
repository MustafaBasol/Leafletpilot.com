# LeafletPilot Demo Remediation Roadmap

## Prioritization baseline

- **P0 (3):** deterministic demo/reset, real product assets, credible template pack/preview.
- **P1 (9):** disabled-delivery truthfulness, throttle isolation, exposed placeholders, mock settings/bot/dashboard/audit, simulated draft save, incomplete template administration.
- **P2 (5):** catalog depth, global export discoverability, form polish, 404 handling, customer-language consistency.
- **P3 (2):** reporting and full visual template editor.

The backend campaign → preview → PDF/PNG export path is already functional. Remediation should protect and populate that path instead of replacing it.

## Phase 20D-1 — Demo blockers: deterministic demo tenant and assets

**Recommended first implementation PR. Priority:** P0. **Estimated size:** L.

Deliver:

- Add an explicit demo-tenant marker/allow-list and guarded, idempotent seed/reset commands.
- Preserve all non-demo tenants and refuse ambiguous targets.
- Package license-safe synthetic product imagery; remove `example.com` image dependencies.
- Seed a golden completed campaign plus ready PDF/PNG fallback artifacts, or generate and verify them as part of reset.
- Print and verify expected counts after seed/reset.
- Keep current production seed refusal for generic development fixtures.

Exact likely files:

- Modify `backend/scripts/seed_dev_data.py` and `backend/tests/test_seed_dev_data.py` or extract their reusable fixture builders.
- Add `backend/scripts/seed_demo_tenant.py` and `backend/scripts/reset_demo_tenant.py`.
- Add `backend/tests/test_seed_demo_tenant.py` and `backend/tests/test_reset_demo_tenant.py`.
- Add a dedicated demo asset directory and its manifest; update ProductImage fixture URLs/storage keys.
- Update deployment/demo operations documentation only after commands are executable.

Acceptance:

- Seed twice yields identical counts and no duplicates.
- Reset twice is safe and deterministic.
- A separate synthetic customer tenant remains byte-for-byte/row-for-row unchanged.
- Invalid, absent, non-demo, or production-customer targets are refused.
- Every seeded product image is locally available.
- Login → campaign → preview → export → history/download works immediately after reset.

## Phase 20D-2 — Template foundation and six-sector pack

**Priority:** remaining P0 plus DRA-012. **Estimated size:** XL, split into foundation and content PRs if needed.

Deliver:

- Define a validated, versioned configuration contract for the renderer-supported template fields.
- Connect `#/templates/:id` preview to the real renderer with a controlled preview dataset.
- Add the six templates from `DEMO_TEMPLATE_PACK.md` with local assets and example campaigns.
- Add structured create/edit UI for supported fields and enforce global/market permissions.
- Verify preview/export parity and overflow/missing-asset behavior.

Likely areas: template schemas/model/service/routes, preview renderer, template pages/API, demo fixture builders, renderer/template tests, and design assets.

Acceptance: all six templates appear, preview, attach to campaigns, export PDF/PNG, and retain market/global scope correctly.

## Phase 20D-3 — Activation, delivery-state, and demo reset operations

**Priority:** DRA-004 and DRA-005. **Estimated size:** M.

Deliver:

- Represent disabled invitation delivery explicitly instead of converting it to a failed send.
- Explain the controlled SMTP prerequisite in Platform Admin and expose no misleading retry state.
- Keep token lifecycle/acceptance independent from email transport tests.
- Namespace signup and invitation-preview throttle buckets so one flow cannot consume the other's allowance.
- Finalize the pre-demo reset command, synthetic SMTP mailbox cleanup, and operator checklist.

Likely files: `backend/app/services/invitation_email.py`, `backend/app/api/routes/platform.py`, `backend/app/api/routes/public.py`, `backend/app/api/routes/auth.py`, Phase 20C tests, `src/pages/platform/PlatformMarketDetail.jsx`, and platform labels/tests.

Acceptance: disabled is rendered as disabled; controlled SMTP sent/failed states remain accurate; valid invitation preview is unaffected by public signup traffic; invalid/expired/revoked/accepted/existing-user tests all pass.

## Phase 20D-4 — UX truthfulness and polish

**Priority:** remaining P1/P2. **Estimated size:** L across small PRs.

Deliver in separate focused PRs:

- Hide or clearly gate `#/markets`, `#/files`, `#/reports`, and `#/bot-connections` until real.
- Persist `#/settings` through market profile/brand APIs.
- Remove or implement the simulated campaign “Save draft” action.
- Add a dedicated Platform Audit page.
- Back dashboard activity/summary with real data or narrow the UI claims.
- Complete alias/image management, global export discoverability, user-facing form labels, action errors, and explicit 404 behavior.
- Choose and consistently apply the customer-demo locale.

Acceptance: no visible control reports success without persistence; no navigation item leads to a generic “next phase” screen; error/loading/empty states are present on all demonstrated pages.

## Phase 20D-5 — Final smoke and external acceptance

**Priority:** release gate. **Estimated size:** M.

Deliver:

- Add an automated isolated smoke for login → products → templates → create campaign → preview → PDF/PNG → history/download.
- Add Phase 20C smoke coverage for token states and existing-user acceptance with email transport mocked separately.
- Run desktop and agreed mobile/tablet viewport checks through a browser-capable environment.
- Reset twice and rehearse the 7-minute flow twice.
- Validate production configuration contracts and migration head.
- After normal deployment, conduct a separately authorized production read-only smoke without data mutation.

External-show acceptance requires:

- All P0 resolved.
- No demonstrated P1 unresolved.
- Six templates and local assets available.
- Reset is deterministic and tenant-safe.
- Core smoke passes twice.
- Presenter fallbacks exist and are downloadable.
- Browser viewport review passes.
- Production read-only smoke is recorded separately.

## Deferred P3

- Reporting/analytics API and page.
- Full drag-and-drop visual template editor.

These must not delay the curated-template customer demo.

## Commands for the next PR

```powershell
git switch main
git pull --ff-only origin main
git switch -c feature/demo-data-reset
```

Before publishing that PR:

```powershell
npm.cmd run validate
npm.cmd run test:platform
npm.cmd run build
npm.cmd run smoke
cd backend
.\.venv\Scripts\python.exe -m pytest
cd ..
git diff --check
```

Do not merge or deploy from this audit roadmap.

## Phase 20D-1 operator contract

The deterministic demo tenant is operated only through `app.scripts.demo_tenant`; there is no customer-facing reset endpoint. Configure `DEMO_OPERATIONS_ENABLED=false` by default. In an isolated rehearsal environment, set `DEMO_MARKET_ID`, `DEMO_MARKET_SLUG`, `DEMO_OWNER_EMAIL`, and (only for first bootstrap) `DEMO_OWNER_INITIAL_PASSWORD` together, then run `inspect`, `reset --dry-run`, `reset --confirm`, `seed`, `generate-exports`, and `verify`. The command refuses missing or mismatched market identity, never selects a first/latest/all market, and never logs credentials. A missing owner can only be created with the explicit synthetic bootstrap secret; production refuses new demo-owner creation.

Reset deletes only deterministic demo IDs (the 16 `LP-DEMO-*` products, their aliases/images, the two `demo-*` templates, the deterministic category/brand IDs, the golden campaign and its dependent rows, and `demo_*` activity rows). It preserves same-market unrelated categories, brands, campaigns, exports, files, users, signup requests, invitations, and platform-admin records. Files are collected and path-checked first, the database transaction is committed, and only then are verified demo-owned files removed. A cleanup error is surfaced after commit; repeating reset removes remaining files only from the exact demo asset subtree or the golden campaign export subtree.

For an isolated disposable environment: `alembic upgrade head`; `python -m app.scripts.demo_tenant inspect`; `python -m app.scripts.demo_tenant seed`; `python -m app.scripts.demo_tenant seed`; `python -m app.scripts.demo_tenant generate-exports`; `python -m app.scripts.demo_tenant verify`; `python -m app.scripts.demo_tenant reset --confirm`; `python -m app.scripts.demo_tenant reset --confirm`; `python -m app.scripts.demo_tenant seed`; `python -m app.scripts.demo_tenant generate-exports`; `python -m app.scripts.demo_tenant verify`. Install the repository Playwright version's Chromium before export validation. Keep production demo operations disabled unless a dedicated, explicitly allow-listed demo tenant is intentionally operated; never use real customer data.
