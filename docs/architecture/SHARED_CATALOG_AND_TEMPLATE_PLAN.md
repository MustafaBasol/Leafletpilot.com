# Shared Catalog and Template Architecture Plan

Status: Phase B complete; safe to continue to Phase C after review.

This is a living architecture and implementation record for the shared global catalog and template library. Work is limited to synthetic or isolated test data. Production access, deployment, merge, and destructive data changes are out of scope.

## Phase A record

- Status: complete.
- Branch: `feature/shared-global-catalog-template-architecture`, based on the latest `main`.
- Baseline Alembic head: `20260711_0012` (`backend/alembic/versions/20260711_0012_promo_flyer_foundations.py`).
- Baseline backend tests: `110 passed, 30 skipped, 5 warnings`.
- Baseline compile check: the requested command was attempted; the existing repository `__pycache__` files are permission-protected on this workstation. The Phase B verification will use a writable `PYTHONPYCACHEPREFIX`.
- Baseline `git diff --check`: clean.
- Unrelated worktree state: untracked root `artifacts/` directory preserved.
- Phase A commit: pending creation after this document is reviewed and validated.

## Current-state inventory

### Product and catalog tables

`backend/app/models/catalog.py:29-191` defines `Brand`, `Category`, `Product`, `ProductAlias`, and `ProductImage`.

`Product` currently contains:

- `id`, `market_id`, `brand_id`, `category_id`;
- `name`, `short_name`, `barcode`;
- `package_size`, `package_type`;
- `regular_price`, `promo_price`, `currency`;
- `sort_order`, `badge_text`;
- `is_global`, `is_active`, `quality_score`;
- `usage_count`, `last_used_at`, timestamps.

The table enforces `(is_global=true and market_id is null) or (is_global=false and market_id is not null)` and indexes market, brand, category, barcode, name, active state, and global state.

`ProductAlias` (`catalog.py:148-165`) belongs to one `Product`, stores `alias`, `normalized_alias`, and optional `source`, and has a per-product normalized-alias uniqueness constraint.

`ProductImage` (`catalog.py:167-191`) belongs directly to one `Product` and stores:

- `storage_key`, optional `url`;
- `image_type`, `mime_type`, `size_bytes`;
- `width`, `height`, `has_transparent_background`;
- `quality_status`, `is_primary`, and creation timestamp.

The current catalog service accepts image metadata in `ProductCreate` and persists `ProductImage` records (`backend/app/services/catalog.py:226-236`). There is no dedicated product-image upload endpoint or signature/type validation path yet. Rendering reads `storage_key` through the safe storage resolver (`backend/app/services/preview_renderer.py:291-300` and `backend/app/services/rendering.py:77-83`). Existing image storage keys must therefore be preserved exactly.

`Brand` and `Category` both support global rows (`market_id=null`, `is_global=true`) and market-scoped rows. `Category` also has `parent_id`, ordering, color, and icon. Existing filtering is implemented by `apply_scope_filters` in `backend/app/services/catalog.py:45-61`; when `include_global=true`, it returns the current market’s rows plus global rows.

### Templates

`backend/app/models/template.py:17-48` defines one `templates` table with:

- `id`, `market_id`;
- `name`, `slug`, `description`, `template_type`;
- `is_global`, `is_active`;
- `config_json`, timestamps.

The same global/market scope check and partial unique slugs are used for templates. `backend/app/services/templates.py:18-28` applies global-plus-market reads. `backend/app/api/routes/templates.py:46-81` currently allows market admins to create and update templates, and the service’s `get_template` includes global rows. Global mutation protection is not yet enforced there.

Campaigns already preserve template identity: `backend/app/models/campaign.py:53-125` stores `Campaign.template_id` as a foreign key to `templates.id`.

### Campaign compatibility

`CampaignItem.product_id` is a nullable foreign key to `products.id` (`backend/app/models/campaign.py:127-160`). Matching and rendering rely on this relationship through `backend/app/services/product_matching.py`, `backend/app/services/campaign.py`, `backend/app/services/campaign_rendering.py`, and `backend/app/services/preview_renderer.py`. Existing campaign item IDs and product IDs must remain valid.

### Existing mutation and filtering routes

Market-authenticated routes in `backend/app/api/routes/catalog.py` currently expose mutation of brands, categories, products, and aliases through `require_market_role`. The service methods call scoped getters with `include_global=true`, so a market user can currently reach a visible global record and attempt to update it (`catalog.py:239-276`). This is a required Phase B authorization fix.

Template mutation has the same issue: `POST /templates` and `PATCH /templates/{template_id}` use market-admin authorization but the service can resolve global templates (`backend/app/api/routes/templates.py:46-81`, `backend/app/services/templates.py:64-68,124-138`).

### Market, plans, permissions, and storage

`backend/app/models/market.py:21-58` currently has no subscription-plan field. It has market identity, branding, `promo_profile_json`, currency/language/timezone, lifecycle, onboarding, and default template fields.

`backend/app/core/roles.py:4-36` defines `market_admin`, `market_staff`, and `viewer` plus a role permission matrix. `backend/app/api/deps.py:195-223` provides role and market-membership helpers, including lifecycle checks. There is no entitlement resolver or server-side plan limit enforcement.

Storage safety currently exists for export keys: `backend/app/services/rendering.py:77-83` rejects absolute paths and traversal segments. Product-image uploads are not yet implemented, so Phase B will define an isolated metadata/override foundation without exposing arbitrary filesystem paths.

### Migrations and seeds

Alembic migrations are linear through `20260711_0012`; the current head is verified above. Initial catalog tables are created in `20260702_0001_initial_core_catalog_models.py`; campaigns in `20260702_0002_campaign_workflow_models.py`; templates in `20260704_0003_template_models.py`; platform operations and flyer foundations follow in later revisions. Seed conventions in `backend/scripts/seed_dev_data.py` and `backend/app/scripts/demo_tenant.py` create global catalog/template rows and market-scoped products.

## Architecture decision record

### Option A — separate `GlobalProduct` and `MarketProduct` tables

This would make canonical identity and market presentation explicit, but would require moving or adapting all current direct `Product` relationships. `CampaignItem.product_id`, `ProductImage.product_id`, `ProductAlias.product_id`, brand/category foreign keys, matching queries, preview queries, seed scripts, and existing API response shapes would all need compatibility adapters or foreign-key changes. It provides a clean long-term model but creates a high-risk migration and rollback surface.

### Option B — preserve `Product` as the canonical/shared product layer and add a market association/override layer

This preserves existing global `Product` IDs and relationships while adding market-specific state separately. A new additive `market_products` association will reference a canonical `products.id` when adopted and will support private market rows with nullable canonical linkage. Market-specific name, image, price, promo, currency, badge, stock note, category, ordering, and active state live on the association/override layer. Existing market-scoped `Product` rows remain intact as legacy compatibility records during staged migration.

### Selection

Select **Option B** as the least risky architecture for this repository.

Evidence:

- `CampaignItem.product_id` already points directly to `products.id`; preserving that key avoids a broad campaign migration.
- `ProductImage` and `ProductAlias` both point directly to `Product`; canonical global rows can continue to own those relationships while market overrides are added separately.
- Existing brand/category foreign keys and global/market filtering already operate on `Product`, so the new layer can be introduced behind catalog services.
- Matching currently searches `Product` rows and aliases; a compatibility resolver can search canonical products plus market associations without changing historical items.
- Rendering already receives a product from a campaign item; a deterministic resolver can provide effective display data without changing campaign foreign keys.
- Additive migrations preserve rows, IDs, storage keys, template IDs, and campaign references, making rollback materially simpler than a table split.
- Option B delivers the required adoption and override behavior faster while retaining a future path to physically split tables if later evidence justifies it.

## Target entity relationships

```text
Market 1──* MarketProduct *──0..1 Product (canonical/shared)
                         └── legacy/private compatibility data
Product 1──* ProductAlias
Product 1──* ProductImage
Product *──1 Brand
Product *──1 Category
MarketProduct *──0..1 Category (market override)
Campaign 1──* CampaignItem *──0..1 Product (legacy-compatible FK)
Campaign *──1 Template
Template 0..1──1 Template (source_template_id for clones)
Market *──1 entitlement plan
```

Phase B will add `market_products` with: `id`, `market_id`, nullable canonical `product_id`, nullable legacy product reference where needed for backfill, private-product identity fields, market display/price/promo/currency/badge/stock/order/active fields, nullable category override, image-override metadata, and lineage/timestamps. A unique `(market_id, product_id)` constraint will prevent duplicate adoption. The exact column names and constraints will be finalized in the migration implementation without dropping existing columns.

Templates will remain in the existing table. Additive fields are planned for `owner_scope`/derived ownership, `source_template_id`, `source_version`, `version`, `published_at`, `allowed_plan_codes` (or equivalent JSONB), and clone snapshot/config data where required. Existing `Campaign.template_id` remains unchanged.

## Ownership and permission rules

- Platform admins own and mutate global products, images, brands, categories, and templates.
- Market users may read eligible global records but cannot mutate them through any market route.
- Market admins/staff may mutate their own market associations and private products according to entitlement capabilities.
- Viewers remain read-only.
- Backend entitlement and ownership checks are authoritative; frontend guards only improve UX.
- All market queries require authenticated membership and the requested market ID.

## Category architecture

Global categories remain the shared taxonomy. Existing market categories remain supported as market-local taxonomy. A market product may reference a global category through its canonical product or set a market category override.

- Search global catalog by product name, barcode, brand, alias, and category labels.
- Market catalog filtering includes global-category matches plus market-category overrides.
- Adoption copies the canonical product association and permits a market category override.
- Rendering uses market category override, then canonical global category, then `Uncategorized`.
- Deactivated global categories are excluded from new selection but retained for historical rendering.

## Template architecture and behavior

The existing `Template` table is retained. Global templates are platform-owned. Market templates are market-owned. A clone records `source_template_id`, source version, and a snapshot/config so later global changes do not mutate the clone.

- Global updates affect eligible markets using the live global template.
- Clones and private templates do not receive automatic source updates.
- Global deactivation blocks new use and default selection but preserves historical campaign references.
- Market users can edit only market-owned records.

## Initial entitlement matrix

Static configuration is centralized initially; billing synchronization is explicitly deferred.

| Capability | Starter | Growth | Pro |
|---|---:|---:|---:|
| Global catalog access | yes | yes | yes |
| Private products | 25 | 250 | unlimited |
| Product image overrides | no | yes | yes |
| Global templates | yes | yes | yes |
| Global template cloning | no | yes | yes |
| Private templates | 0 | 5 | unlimited |
| Custom templates | no | no | yes |
| Branding/logo assets | 1 | 3 | unlimited |
| Monthly exports | 10 | 50 | 250 |

Markets without an assigned plan resolve to the safest default: global catalog read access, no private products, no image overrides, global templates only, no cloning/custom templates, one branding asset, and the lowest export limit. The resolver will expose capability names and numeric limits without coupling callers to plan labels.

## Migration, backfill, and rollback

1. Add the association and entitlement schema without dropping or renaming existing tables/columns.
2. Preserve every existing `Product`, `ProductImage`, `ProductAlias`, `Template`, `Campaign`, and `CampaignItem` row and identifier.
3. Backfill canonical global associations from `Product.is_global=true` rows.
4. Backfill market associations from existing market-scoped products, retaining a legacy source ID and copying all market-specific values and image references.
5. Produce row-count and orphan verification in an isolated migration test/rehearsal.
6. Add compatibility reads and deterministic effective-product resolution before changing existing writes.
7. Keep legacy reads available until Phase G confirms campaign, import, matching, preview, and export parity.
8. Roll back by disabling new association reads/writes and reverting the additive migration; no destructive downgrade or data deletion is permitted.

## Exact Phase B scope

- Add one additive Alembic revision for `market_products` and plan/entitlement storage required by the resolver.
- Add SQLAlchemy models, exports, schemas, and compatibility mapping.
- Add centralized static entitlement definitions and a market capability resolver.
- Add catalog search/read/adopt/private-create service foundations.
- Reject market updates/deletes of global products, brands, categories, and templates.
- Add deterministic effective name/image/category resolution.
- Preserve current campaign/template foreign keys and legacy product reads.
- Add focused backend tests only; no Platform Admin UI or market adoption UI.

## Phase B tests

- Eligible market reads/searches global products.
- Market mutation of global product is rejected.
- Global product adoption succeeds once and duplicate adoption is rejected.
- Market price/promo values are independent from canonical product data.
- Entitled private creation succeeds; limit enforcement rejects excess creation.
- Name precedence: market override > global name > private name.
- Image precedence: market override > approved global image > placeholder.
- Category precedence: market override > global category > uncategorized.
- Cross-market access is denied.
- Existing campaign rendering and legacy product reads remain valid.
- Migration preserves row counts, IDs, storage keys, aliases, images, and campaign references.

## Risks and unresolved items

- Existing market-scoped products may not have reliable canonical matches; backfill must report ambiguous matches rather than silently merge them.
- Product-image upload validation is not currently implemented and must remain out of scope except for safe metadata/override boundaries in Phase B.
- Existing global mutation behavior must be hardened without breaking legitimate market-owned edits.
- Template plan visibility and version publication need API shape validation during Phase E.
- The provisional limits require later product/billing confirmation; they are documented defaults, not billing commitments.

## Phase B record

- Status: complete.
- Objective: deliver the additive backend shared-catalog foundation without changing campaign or template foreign keys.
- Migration: `20260712_0013_shared_catalog_foundation.py`; adds nullable `markets.subscription_plan`, creates `market_products`, and backfills existing market-scoped products as legacy-compatible private associations.
- New model/service surface: `MarketProduct`, `MarketProductRead`, adoption/private-create schemas, `services.entitlements`, global search, adoption, private creation, effective-product resolution, and global mutation guards.
- Compatibility: existing `Product`, `ProductImage`, `ProductAlias`, `CampaignItem.product_id`, `Template.id`, and campaign template references remain unchanged. Existing market-scoped product rows are preserved and retain their storage/image relationships.
- Authorization: market catalog and template services now reject global mutations; new adoption/private endpoints require authenticated market mutation roles and entitlement checks.
- Focused tests before PostgreSQL rehearsal: `12 passed, 2 skipped, 2 warnings` (`tests/test_shared_catalog_foundation.py` plus catalog API tests).
- Full backend tests before PostgreSQL rehearsal: `117 passed, 30 skipped, 5 warnings`.
- Compile verification: source compilation passed via a no-write compile check (`compile-source-ok`). The literal `python -m compileall app` remains affected by permission-protected existing `__pycache__` paths on this workstation.
- Alembic one-head check: passed; `20260712_0013 (head)`.
- `git diff --check`: passed.
- Isolated PostgreSQL upgrade: completed after the dedicated rehearsal below.
- Deviations: image upload/signature validation was not implemented because no product-image upload endpoint exists in the current repository; Phase B only preserves existing metadata/storage keys and defines safe override fields.
- Risks discovered: the migration backfill currently copies legacy product presentation values into associations but intentionally leaves canonical matching/relinking to the later compatibility-read phase; ambiguous identity matches must not be auto-merged.
- Unresolved: database-backed migration row-count verification and adoption API integration tests require isolated PostgreSQL; platform global catalog routes remain Phase C.

## Phase B PostgreSQL 16 migration and preservation rehearsal

- Status: passed on a disposable local PostgreSQL `16.14` container bound only to `127.0.0.1:55432`. It used the synthetic `leafletpilot_rehearsal` database; no production service or customer data was accessed.
- Commands: `alembic upgrade 20260711_0012`; seed fixed synthetic legacy rows; `alembic upgrade 20260712_0013`; `alembic current`; `alembic heads`; `alembic downgrade 20260711_0012`; `alembic upgrade 20260712_0013`. Each Alembic command used a local `DATABASE_URL` for the disposable database.
- Initial finding and fix: the first PostgreSQL execution exposed an extra closing parenthesis in the idempotent `market_products` backfill SQL. PostgreSQL rolled the transaction back cleanly (no `market_products` table and Alembic remained at `20260711_0012`). The migration was corrected before the successful rerun.
- Seed before upgrade: 2 markets, 2 brands, 2 categories, 4 products (2 global and 2 market-scoped), 2 `ProductImage` rows with storage keys, 2 aliases, 2 templates, 2 campaigns, and 3 campaign items. All IDs were fixed UUIDs for exact comparison.
- Pre/post preserved counts: markets 2/2; brands 2/2; categories 2/2; products 4/4; product images 2/2; aliases 2/2; templates 2/2; campaigns 2/2; campaign items 3/3. The upgrade added 2 legacy `MarketProduct` rows; exercising adoption added one further association, for 3 total.
- Preserved foreign keys: all four legacy `Product.id` values remained unchanged; image IDs/storage keys `...0501`/`products/global-espresso.webp` and `...0502`/`products/market-one-juice.webp` remained unchanged; alias IDs `...0601` and `...0602` remained unchanged; template IDs `...0701` and `...0702` remained unchanged; campaign item IDs `...0901`, `...0902`, and `...0903` retained product IDs `...0401`, `...0403`, and `...0402`, respectively.
- Backfill result: legacy product `...0403` became a Market 1 association with name `Market One Legacy Juice`, price `2.99`, promo `1.99`, and its category override; legacy product `...0404` became the equivalent Market 2 association with price `1.49`. Both legacy product rows themselves remained readable.
- Constraints and isolation: a first global-product adoption stored isolated Market 1 price/promo `5.49/4.49`; the duplicate adoption returned HTTP 409; an attempt by Market 2 to adopt Market 1's non-global legacy product returned HTTP 404. The unassigned-plan resolver returned global catalog read access, zero private products, and no image override.
- DB-backed focused tests: `14 passed, 2 warnings` with `TEST_DATABASE_URL` set to the disposable PostgreSQL database.
- DB-backed full backend tests: `146 passed, 1 skipped, 5 warnings` with the same configured `TEST_DATABASE_URL`.
- Downgrade/re-upgrade: `20260712_0013 -> 20260711_0012` succeeded and retained 4 products, 2 images, 2 aliases, 2 templates, 2 campaigns, and 3 campaign items. It intentionally drops the additive `market_products` table and its post-upgrade association data, so it is a structural/schema rollback only. Re-upgrade restored the two deterministic legacy backfill rows and again passed all preservation, duplicate-adoption, cross-market, and entitlement checks.
- Alembic: `current` and `heads` both reported the sole head `20260712_0013 (head)` after re-upgrade.
- Risk: do not use the destructive Alembic downgrade as an operational rollback once markets have created new associations; operational rollback remains feature-disable/read fallback plus a backup/restore decision. This behavior is now demonstrated, not merely assumed.
- Phase C gate: safe to begin. The migration and legacy-data compatibility gate is now passed; Phase C must still preserve the described rollback boundary.

## Exact next steps

1. Commit the Phase B backend foundation and this documentation update separately from Phase A.
2. Push the feature branch and create a draft PR targeting `main`.
3. Implement Phase C platform global catalog management on this branch; retain the migration's structural-rollback limitation in its operator guidance.
4. Keep the PR draft; do not mark ready, merge, or deploy.

## Phase C — platform admin global catalog management

- Status: implementation complete for the first platform-admin management slice; isolated acceptance and full CI rehearsal remain required before Phase D.
- API design: dedicated authenticated routes under `/platform/catalog/categories`, `/platform/catalog/brands`, `/platform/catalog/products`, and `/platform/catalog/products/{id}/images`. These routes use `get_current_platform_admin` and do not depend on market membership.
- UI design: Platform Admin navigation now exposes Global catalog with category, brand, and product list/search/create/deactivate flows and loading, empty, and error states.
- Storage design: uploaded bytes are accepted only as PNG, JPEG, or WebP with MIME, signature, and 10 MiB checks. Keys are generated under `global/catalog/{product_id}/`; raw filesystem paths are never returned. Primary designation clears other primary images.
- Permission boundaries: existing `/catalog` market routes retain their global-mutation denial. Platform catalog routes require a platform-admin bearer token; market tokens do not satisfy that dependency.
- Files changed: `backend/app/api/routes/platform_catalog.py`, `backend/app/schemas/platform_catalog.py`, `backend/app/api/router.py`, `src/api/platformApi.js`, `src/pages/platform/PlatformAdminLayout.jsx`, `src/pages/platform/PlatformCatalog.jsx`, and `src/App.jsx`.
- Migration: none; existing global catalog tables and image metadata are sufficient, preserving Product, ProductImage, ProductAlias, and CampaignItem IDs.
- Tests/evidence: source syntax check passed, frontend production build passed, existing focused catalog/foundation tests passed (`12 passed, 2 skipped`). Full backend and isolated PostgreSQL acceptance are pending in this workstation pass.
- Deviations/known limitations: image transport is a raw image request (`Content-Type` plus request body) to avoid adding a multipart dependency; image dimensions/decoding are deferred. The first UI slice exposes create/deactivate and search; edit forms, previews, replace/remove controls, and complete localized copy remain follow-up work within Phase C.
- Exact Phase D next steps: complete edit/image-management UI, add dedicated platform route tests and isolated PostgreSQL seed/acceptance evidence, update PR metadata, then review unresolved threads before considering Phase D.

## Phase C continuation evidence

- Status: implementation slice extended; Phase C is not declared complete until CI, disposable PostgreSQL/API acceptance, and browser UI acceptance are green.
- Exact routes: `GET/POST /platform/catalog/categories`, `PATCH/DELETE /platform/catalog/categories/{category_id}`; equivalent brand routes; `GET/POST /platform/catalog/products`, `PATCH/DELETE /platform/catalog/products/{product_id}`; `POST /platform/catalog/products/{product_id}/images`; `PATCH /platform/catalog/products/{product_id}/images/{image_id}/primary`; `DELETE /platform/catalog/products/{product_id}/images/{image_id}`. Authenticated image content is available through an internal preview endpoint and never exposes a filesystem path in the UI.
- UI pages: `#/platform/catalog` contains category and brand management plus a global product editor with canonical name, barcode/SKU, brand, category, package fields, aliases, active state, validation/error/save states, and image preview/upload/replace/primary/remove controls. Pricing, promo, and currency fields are intentionally absent.
- Storage contract: PNG/JPEG/WebP only; MIME and signature checks; 10 MiB limit; keys are isolated below `global/catalog/{product_id}/`; primary selection is exclusive; replace uploads a new object and removes the prior object.
- Tests: dedicated route/security contract tests now cover the registered CRUD/image surface, unauthenticated denial, and rejection of a market bearer token. Focused run: `30 passed, 2 skipped, 2 warnings` including existing catalog/foundation coverage. Source syntax and frontend build passed. DB-backed route mutation/image matrix remains pending because no disposable PostgreSQL acceptance was run in this continuation.
- Acceptance evidence: no production access, deployment, merge, or customer data. No browser screenshot evidence or isolated PostgreSQL seed evidence is claimed yet. Existing ignored `artifacts/` remains preserved.
- Deviations/known limitations: raw-body image upload remains intentional because the current environment lacks multipart support; image decoding/dimensions remain deferred. Full backend pytest, frontend validate/platform/smoke, Docker checks, and CI completion still need to run.
- Phase D entry criteria: CI green; full route/image tests plus isolated PostgreSQL API seed pass; isolated UI/browser evidence passes with no console errors; market-user denial and market global-mutation denial are proven; docs and PR body reflect those results; no unresolved blocking review feedback.

## Phase C verification update

- GitHub Actions run `29190597011`: backend, frontend, and Docker checks all passed.
- Disposable PostgreSQL 16.14 on `127.0.0.1:55433`: focused platform/catalog suite `32 passed, 1 warning`; container removed after the run. The full backend run against this database did not finish within the run window and is not counted as passed.
- Frontend: `npm.cmd run validate` passed; `npm.cmd run test:platform` passed (`15 passed`); `npm.cmd run build` passed; `npm.cmd run smoke` passed.
- Infrastructure: `python -m compileall app` passed; Alembic sole head is `20260712_0013 (head)`; `git diff --check` passed. Production Compose config validation was attempted read-only with placeholder local values but stopped on additional required environment variables; no services were started.
- Completion decision: Phase C remains incomplete. Missing evidence is browser/UI acceptance with screenshots and no-console proof, a completed full backend run against configured `TEST_DATABASE_URL`, and a complete DB-backed mutation/image route matrix beyond the focused security/contract suite. Phase D is not safe to begin.

## Phase C final verification pass (2026-07-12)

- Latest CI for HEAD `05c40963deabf003b5a486532608b4bd08d4d95e`: passed. Validation run `29190847386` reports backend, frontend, and Docker success.
- Disposable PostgreSQL 16.14: migrations applied through `20260712_0013`; `alembic current` and `alembic heads` both report `20260712_0013 (head)`. Full backend suite completed with `165 passed, 4 warnings` using `TEST_DATABASE_URL` and an isolated pytest temp directory. The initial attempt exposed only a host temp-directory permission problem; no test failure remained after isolating that directory.
- Additional checks: `python -m compileall -q app` and `git diff --check` passed. Previously recorded frontend validation, platform tests (`15 passed`), build, and smoke checks remain green.
- Browser evidence: local frontend platform-admin login page loaded at `http://127.0.0.1:5173/#/platform/login`; no console errors were observed. Screenshot: `artifacts/phase-c-platform-login.jpg`. Authenticated seeded catalog CRUD/image browser acceptance was not completed, so this is partial UI evidence only.
- API/image acceptance: the complete seeded HTTP mutation/image lifecycle matrix (6 categories, 8 brands, 20 products, 10 images, 2 markets) was not completed in this pass. Route/security contract coverage and full regression coverage pass, but this does not substitute for the requested seeded API evidence.
- Cleanup policy: the disposable PostgreSQL container and isolated test storage are removed after validation; accepted image replacement is upload-new then remove-old, and failed/invalid uploads must not create a row or object. This policy is not yet backed by the requested seeded lifecycle transcript.
- Known limitations: production Compose validation still requires a complete local environment file; no production services were started. The UI uses an authenticated preview fetch for images, but browser acceptance of the authenticated catalog surface remains outstanding.
- Completion decision: Phase C remains incomplete. Phase D is not safe to begin until seeded API mutation/image acceptance, authenticated browser acceptance with deterministic screenshots, and any blocking review feedback checks are complete.

## Phase C final verification pass 2 (2026-07-12)

- Current CI: GitHub Actions Validation run `29191325115` is green for the current HEAD before this acceptance commit: backend, frontend, and Docker all passed.
- Route hardening: global category and product canonical-name duplicate protection was added. Product create/update/deactivate and alias/image responses now eagerly load or explicitly serialize relationships, preventing async lazy-load failures in real HTTP responses. Raw `storage_key` and `url` values are omitted from platform API image payloads; authenticated preview URLs remain available.
- Seeded HTTP acceptance: disposable PostgreSQL 16.14, isolated `LOCAL_STORAGE_DIR`, 2 markets, 2 market users, 6 categories, 8 brands, 20 products, aliases, barcodes, and MarketProduct associations. Real ASGI HTTP requests passed: `19 passed, 2 warnings`. Status evidence includes 401 unauthenticated/market-token denial, 201 creates, 200 edits/reactivations/deactivations, 409 duplicate category/brand/product name/barcode rejection, 404 removed-image fetch, 415 invalid MIME, 422 mismatched signature, and 413 oversized upload.
- Image lifecycle: PNG/JPEG/WebP upload, exclusive primary selection, fresh API read, authenticated content fetch, non-primary/primary removal, no raw path payload, isolated `global/catalog/{product_id}/` namespace, and file-count checks for three successful files, no failed-upload file delta, and one-file removal delta passed. The disposable container was removed after the run.
- Full backend: `166 passed, 5 warnings` with `TEST_DATABASE_URL`; frontend validation passed, platform tests `15 passed`, build passed, smoke passed; compile-only check and `git diff --check` passed. Alembic sole head remains `20260712_0013 (head)`.
- Browser evidence: login-page evidence remains at `artifacts/phase-c-platform-login.jpg`; the authenticated seeded catalog browser matrix and requested CRUD/image screenshots were not completed in this pass. No-console evidence is therefore only for the public platform login page.
- Permission evidence: unauthenticated and normal market bearer tokens received HTTP 401 on platform category/product routes and market tokens could not mutate platform products/brands. Cross-market association isolation and expired-token transcript remain unrecorded.
- Review state and CI: review decision and unresolved thread count must be read from GitHub thread-level data before completion; no merge/deploy/production action occurred. Production Compose validation remains blocked by missing complete local environment values, with no services started.
- Completion decision: Phase C remains incomplete because authenticated browser acceptance, complete review-thread certification, production Compose validation, and a broader market-route no-global-mutation transcript remain outstanding. Phase D is not safe to begin.

## Phase C final verification pass 3 (2026-07-12)

- Final pushed HEAD: `ca9023b23c161e2964b61118b4a914feb4c24069` (documentation-only follow-up to the tested acceptance commit `8ae462d`).
- Current GitHub Actions Validation run `29191970773` for the tested acceptance commit: backend, frontend, and Docker all passed.
- Review-thread certification: GraphQL reports `reviews.totalCount: 0`, `reviewThreads.totalCount: 0`, unresolved threads `0`, and `reviewDecision: null`.
- Final decision: Phase C remains incomplete solely because authenticated seeded browser catalog acceptance/screenshots and production Compose validation were not completed; Phase D is not safe to begin.

## Phase C final closure attempt (2026-07-12)

- Disposable browser environment: PostgreSQL 16.14 was started on `127.0.0.1:55437`, migrated through `20260712_0013`, and seeded with the existing synthetic HTTP acceptance seed (`browserc@example.test`, two markets/users, 6 categories, 8 brands, 20 products, aliases, barcodes, and MarketProduct associations). Isolated storage was `artifacts/phase-c-browser-storage/`.
- Browser result: the real Platform Admin login route was reachable at `http://127.0.0.1:5173/#/platform/login` and the login form was captured, but after restarting the Vite server against the disposable API the in-app browser rendered an empty React root. Authenticated CRUD/image screenshots were therefore not captured; the browser gate remains failed. No application console error entries were reported by the browser harness, but that does not substitute for successful authenticated acceptance.
- Screenshot evidence: `artifacts/phase-c-browser-acceptance/platform-login.jpg` is the captured login-page artifact. The requested authenticated catalog, CRUD, image preview, replacement/removal, and market-user navigation screenshots are absent.
- Compose result: the requested `docker-compose.vps.yml` is not present in the repository. A safe synthetic env file was created only under ignored `artifacts/`, and was deleted after the attempt. Docker Compose was unavailable in the final workstation shell (`docker: unknown command: docker compose`); therefore the production combination and Docker builds were not re-run in this closure attempt. No production services or secrets were used.
- Regression totals carried forward: full backend `166 passed, 5 warnings`; focused route/acceptance `19 passed, 2 warnings`; frontend validation passed, platform tests `15 passed`, build and smoke passed; Alembic sole head `20260712_0013 (head)`; review threads `0` and reviews `0`.
- Final decision: Phase C remains incomplete. Exact Phase D entry criteria are: latest HEAD CI green; authenticated Platform Admin browser CRUD/image acceptance with all requested screenshots and no console errors; normal market-user navigation denial; successful validation of both production Compose files with safe synthetic env and no unresolved placeholders; backend/frontend Docker builds passing; documentation and PR body current; and unresolved review threads `0`.

## Phase C diagnostic closure (2026-07-12)

- Empty-root diagnosis: the reported empty `#root` was a diagnostic selector mismatch. `index.html` defines `<div id="app"></div>`, and `src/main.jsx` mounts React with `createRoot(document.querySelector("#app"))`; there is no `#root` element. The authenticated platform route, guard, session storage, API client, and Platform Admin layout are therefore not implicated by this observation. The built frontend also passed its existing validation/build checks. No application code change was required.
- Browser evidence captured before any change: the login route URL was `http://127.0.0.1:5173/#/platform/login` in the prior disposable run; the login screenshot was `artifacts/phase-c-browser-acceptance/platform-login.jpg`. The subsequent local browser sandbox could not connect to the transient local Vite listener and rejected the local file URL, so it did not produce authenticated CRUD/image evidence. The blocker is consequently not closed by browser acceptance; the reproducible source evidence is that `#root` is absent while the application mount contract is `#app`.
- Regression test: `src/pages/platform/platformOps.test.mjs` now asserts the HTML/React mount contract and prevents reintroducing the `#root` probe mismatch.
- Compose source of truth: `docker-compose.vps.yml` is not tracked, not ignored, has no deletion or rename history, and is not referenced by current documentation or CI. Evidence supports “never part of this repository,” not tracked, renamed, generated, or intentionally documented as an operator override. The tracked production source is `docker-compose.production.yml`; `deploy/traefik/docker-compose.traefik.example.yml` is an optional documented override. `docker-compose.production.yml` is standalone-valid according to CI’s safe-env `docker compose -f docker-compose.production.yml config` result.
- CI Docker evidence: Validation run `29193320749` on pushed HEAD `4238cecbc75e51e4312ea65a185d8746313bdd76`, Docker job `86651744014`, ran `docker compose -f docker-compose.production.yml config`, then `docker build -f backend/Dockerfile backend`, then `docker build -f Dockerfile.frontend --build-arg VITE_API_BASE_URL=https://api.example.com/api .`; all succeeded. The local workstation has Docker Engine/Desktop processes, but `docker compose version` returns `docker: unknown command: docker compose`, so the Compose plugin/subcommand is unavailable. No system software was installed and no services were started.
- Phase C decision: incomplete. The selector mismatch is diagnosed and regression-tested; authenticated browser CRUD/image acceptance and its required screenshots remain outstanding. Compose source-of-truth uncertainty is resolved from repository, history, documentation, workflow, and CI evidence; no VPS-only file should be invented. Phase D is not safe to begin.

## Phase D — market global catalog and private product flows

- Status: implementation slice complete locally; full Phase D acceptance is pending. No merge, deployment, or production access occurred.
- Migration: `20260712_0014_market_product_details.py` adds private brand/barcode/SKU/package fields and market-scoped barcode/SKU indexes to `market_products`. Existing product and campaign identifiers remain unchanged.
- API routes: `GET /api/catalog/shared`, `POST /api/catalog/shared/{product_id}/adopt`, `GET /api/catalog/my-products`, `PATCH /api/catalog/my-products/{market_product_id}`, `POST /api/catalog/private-products`, `POST/DELETE /api/catalog/my-products/{market_product_id}/image`; legacy adoption/private routes remain available.
- UI flow: `#/products` now presents `Ürünlerim`, `Paylaşılan Katalog`, and `Özel Ürün Oluştur`. Shared search supports name, barcode, brand, alias, and category matching; adopted state and active eligibility are shown.
- Entitlements: backend uses the centralized resolver for global catalog access, private-product limits, and image overrides. Starter has shared access and no override images; Growth permits overrides; Pro is unlimited for private products. Frontend action availability is supplementary only.
- Precedence: market display/category/price/promo/badge/image override wins over canonical global values, then private values, then placeholder. Override images use `markets/{market_id}/catalog/{market_product_id}/`, validate PNG/JPEG/WebP MIME/signature and 10 MiB maximum, replace atomically, and remove the prior object; removal falls back to the global image.
- Campaign compatibility: `CampaignItem.product_id` remains a `products.id`. Render loading now attaches the market association centrally and preview rendering uses resolved market image/brand/badge values without mutating canonical products.
- Verification so far: full backend `135 passed, 31 skipped, 5 warnings`; focused shared-catalog/route tests `12 passed, 2 skipped, 2 warnings`; preview/foundation tests `12 passed, 1 warning`; frontend validation and production build passed; compile and `git diff --check` passed.
- Limitations: this local pass did not run the requested disposable PostgreSQL 16 Phase D seed/transcript, authenticated browser screenshots, image lifecycle acceptance, or refreshed CI after Phase D. Phase D is therefore not declared complete and Phase E is not safe to begin.
- Exact Phase E next steps: add/execute isolated PostgreSQL acceptance for search/adoption/limits/image isolation/campaign rendering, add frontend interaction tests and authenticated browser evidence, refresh CI and PR review-thread certification, then decide whether Phase D is complete before starting template adoption work.

## Phase D acceptance audit (2026-07-12)

- Current implementation fix: authenticated market image content now resolves storage keys through the shared safe storage-path helper; the seeded lifecycle previously exposed a 500 here and the route was corrected.
- CI baseline: Validation run `29195582514` is green and belongs to HEAD `5280691cbcbb68a33bbf6e80c9ad35095575971b` before the follow-up route fix. A new CI run is required after the fix is pushed.
- Migration rehearsal: disposable PostgreSQL 16 completed `0013 -> 0014 -> 0013 -> 0014`; Alembic current and heads report `20260712_0014 (head)`. Seeded identifiers and campaign references remained intact; the new private-field indexes were created and removed/recreated across the round trip.
- Full backend: `166 passed, 5 warnings` with `TEST_DATABASE_URL` and isolated storage. The image-content route fix was additionally exercised by the seeded HTTP run.
- Seeded Phase D HTTP acceptance: shared search, adoption, duplicate adoption `409`, market overrides/prices, private creation, duplicate barcode `409`, cross-market same-barcode allowance/isolation, image upload/replace/content/remove/fallback, no orphan files, and campaign preview compatibility all passed. Evidence: `artifacts/phase-d-api-acceptance.json`.
- Browser acceptance: public/local browser connectivity was verified and a login screenshot exists at `artifacts/phase-d-browser-acceptance/01-login.png`; authenticated catalog navigation and CRUD/image screenshots could not be completed because the in-app browser session became blocked/blank during local reconnect. Browser acceptance remains failed.
- Decision: Phase D remains incomplete solely because authenticated browser acceptance/screenshots and post-fix CI/review recheck remain outstanding. Phase E is not safe to begin.

## Phase D review closure pass (2026-07-13)

- Review fixes: platform product UUID selections now normalize empty values to `null`; product switching clears staged replacement state; local preview and authenticated image object URLs are revoked on replacement, image changes, and unmount; image requests use the shared expired-platform-session recovery; referenced categories deactivate without losing historical product references; category/brand/product usage counts use grouped queries with zero-count preservation; and the unused `Path` import was removed.
- Template permissions: market users may preview eligible global templates; global template mutation is rejected in `update_template`; market-owned template updates remain allowed. Focused permission coverage passed.
- Tests: focused backend review/route/foundation coverage `28 passed`; full local backend `138 passed, 31 skipped, 5 warnings` because PostgreSQL was unavailable in this workstation session; frontend platform suite `19 passed`; validate, build, smoke, compileall, and `git diff --check` passed.
- Browser acceptance: attempted against the local Vite URL using the reachable browser surface, but the browser namespace returned `ERR_CONNECTION_REFUSED`; no authenticated screenshots were created. Existing evidence remains `artifacts/phase-d-browser-acceptance/01-login.png`. The local PostgreSQL/Docker service was also unavailable, so seeded browser/API acceptance could not be rerun here.
- Review disposition: all 10 Copilot threads were replied to with commit/test evidence and resolved after verification. Final unresolved count: `0`.
- Post-push CI: Validation run `29232347311` passed backend, frontend, and Docker jobs for final HEAD `9828952`.
- Completion decision: Phase D is not complete in this pass; Phase E is not safe to begin. No merge, deployment, or production access occurred.

### Deterministic browser harness

`python scripts/phase_d_playwright.py` is an opt-in local harness. It requires
`PHASE_D_DATABASE_URL` to point to an isolated disposable PostgreSQL 16 database,
starts FastAPI on `127.0.0.1:8100` and Vite on `127.0.0.1:4173`, passes
`VITE_API_BASE_URL=http://127.0.0.1:8100/api`, and waits for `/api/health`, the
authentication endpoint, the platform catalog endpoint, and a frontend `200`
response containing `#app` before launching Playwright. It captures process
logs under the ignored `artifacts/phase-d-browser-acceptance/process-logs/`
directory and terminates both child processes in a `finally` block.

Before startup it runs `alembic upgrade head` and the repeatable
`backend/scripts/seed_phase_d.py` seed. The seed creates the platform admin,
two market users/markets, shared catalog records and images from the existing
synthetic seed, market associations, private market products, aliases, and
campaign-compatible data. It refuses production and requires only the isolated
database URL supplied to the harness.

The previous `ERR_CONNECTION_REFUSED` came from the earlier ad-hoc browser
attempt starting before a live frontend process existed; the Windows launch
command also inherited a `Start-Process` environment collision. The harness
uses `subprocess.Popen`, fixed loopback ports, readiness polling rather than
fixed sleeps, and actionable timeout messages. Browser evidence is written to
`artifacts/phase-d-browser-acceptance/` and remains ignored/uncommitted.

Final CI for harness HEAD `d9b0a2a`: run `29234644031` passed backend,
frontend, and Docker validation. The local browser gate is still pending an
isolated PostgreSQL 16 service; no production access was used.

## Phase D final acceptance (2026-07-13)

- Status: Phase D acceptance passed locally. The deterministic authenticated browser harness completed against disposable PostgreSQL; the database container was removed after the run. No merge, deployment, production access, or production data access occurred.
- Harness probes: frontend `200`; backend health `200`; authentication endpoint `405` (reachable and method-protected); anonymous shared-catalog request `401` (expected).
- Browser evidence: all 12 expected screenshots are present under `artifacts/phase-d-browser-acceptance/`; the harness recorded zero browser errors. The captures include the intended login, platform catalog, product/image, market catalog, campaign preview, and market-navigation checkpoints; some checkpoints intentionally capture loading or transitional UI state.
- Harness correction: `BACKEND_CORS_ORIGINS` and `TRUSTED_HOSTS` are JSON-serialized before subprocess environment injection, fixing the acceptance harness configuration bug.
- API evidence: seeded search, adoption and duplicate-adoption `409`, private-product limits and duplicate-barcode `409`, cross-market isolation, image upload/replace/content/remove/fallback, no-orphan-file protection, and campaign rendering all passed. Evidence: `artifacts/phase-d-api-acceptance.json`.
- CI: Validation run `29245178210` is green for HEAD `ca1a6d1` (backend, frontend, and Docker).
- Review: unresolved review threads `0`; all previously tracked Copilot threads are resolved.
- Readiness: Phase D is ready for the next repository review decision. Phase E is safe to begin as a follow-on phase, but no Phase E implementation, merge, or deployment was performed in this task.

## Phase E — shared template market workflows

- Status: implementation slice complete on `feature/shared-template-market-workflows`; no merge, deployment, or production access occurred.
- Migration: `20260713_0015_shared_template_workflows` is additive after `20260712_0014`. It preserves template IDs and campaign foreign keys and adds status, visibility, minimum plan, category, thumbnail key, source lineage, source version, version, and publish/archive timestamps. Structural downgrade removes only the additive metadata; operational rollback is feature-disable/read fallback plus backup/restore, as with earlier phases.

### Final template model and ownership

The existing single `templates` table remains canonical. Global rows have `market_id=NULL`, `is_global=true`, and are platform-admin managed. Market rows have an owning `market_id`, `is_global=false`, and are market-managed. Adopted rows retain `source_template_id` and `source_version`; their `config_json` is a snapshot of the source at adoption, so later global changes never silently alter market templates or campaigns. `status` is `draft`, `published`, or `archived`; `visibility` distinguishes shared global rows from private market rows.

Published global rows are immutable in place. A platform edit of a published row creates a new draft version, and publishing marks that row as the next version. Campaigns continue to reference the exact `Template.id`, which is the version-safe historical rendering strategy for both global and market-owned templates.

### Entitlement matrix and routes

The Phase D static resolver remains authoritative: Starter can view published global templates but cannot clone or create custom templates; Growth can clone and create up to five private templates; Pro can clone and create unlimited private/custom templates. Shared gallery results are filtered by `minimum_plan`, duplicate adoption returns `409`, and all market routes require authenticated market membership and ownership/role checks.

Platform routes: `GET/POST /api/platform/templates`, `PATCH /api/platform/templates/{id}`, `POST /publish`, `POST /duplicate`, `POST /archive`, and `POST /restore`. Market routes: `GET /api/templates/shared`, `POST /api/templates/shared/{id}/adopt`, `GET /api/templates/my-templates`, and `POST /api/templates/custom`; existing preview and campaign template routes remain compatible.

### UI and campaign compatibility

Platform Admin now has a Global templates page for draft creation, search/list foundation, version display, publish, new-version, archive, and minimum-plan visibility. Markets have shared-template and My Templates sections with already-added state and plan-limit/error messaging. Flyer builder visibility and campaign validation now require published global versions; market-owned adopted/custom rows remain available. Existing campaign product precedence and historical campaign rendering remain unchanged because campaign rows retain their original template and product IDs.

### Acceptance evidence and Phase F entry criteria

Backend compile and full local suite passed: `138 passed, 31 skipped`. Frontend validation passed, platform tests passed (`19 passed`), and production build passed using Vite's writable `--configLoader runner` mode; the default loader was blocked by a pre-existing permission-protected `node_modules/.vite-temp` path. Disposable PostgreSQL/API seed acceptance, deterministic Playwright screenshots, thumbnail upload lifecycle, and CI/review-thread certification remain outstanding for a formal Phase E completion decision. Phase F is not yet safe to begin until those acceptance gates are recorded.

## Phase E formal acceptance closure pass

- Migration rehearsal: passed on disposable PostgreSQL `16.14` at a dedicated local port. `upgrade -> 20260713_0015`, `downgrade -> 20260712_0014`, and `re-upgrade -> 20260713_0015` all passed; `alembic current` and `alembic heads` report the sole head `20260713_0015`.
- Downgrade semantics: structurally reversible only. Existing pre-Phase-E rows and campaign/template foreign keys are preserved, but newly added Phase-E metadata and thumbnail lineage are lossy if the downgrade is used after Phase-E data creation. Operational rollback remains feature-disable/read fallback plus backup/restore.
- PostgreSQL acceptance: deterministic HTTP acceptance passed for global draft/publish/version/archive boundaries, plan-filtered gallery access, adoption lineage, duplicate adoption `409`, market isolation, custom-template entitlement, authenticated preview, and global/market thumbnail upload/replace/remove/signature/namespace behavior. The full PostgreSQL-backed backend suite passed with `170 passed, 5 warnings, 0 skipped`.
- Thumbnail lifecycle: implemented with PNG/JPEG/WebP MIME and signature validation, 10 MiB limit, safe generated keys, authenticated content routes, global namespace `global/templates/{template_id}/...`, market namespace `markets/{market_id}/templates/{template_id}/...`, replace/remove orphan cleanup, and placeholder `404` fallback. Adopted templates receive a copied thumbnail snapshot; source global thumbnails are never used as a live mutable dependency.
- Version safety: published global versions remain immutable; v2 is a new row; adopted templates preserve `source_template_id` and `source_version` and copy current content/thumbnail; campaigns continue to render the exact referenced `Template.id`.
- Browser acceptance: `scripts/phase_e_playwright.py` owns migration, seed, backend/frontend processes, readiness probes, logs, cleanup, and Playwright execution. It completed with 14 screenshots and zero console/page/request errors. Evidence is under `artifacts/phase-e-browser-acceptance/` and remains ignored/uncommitted.
- Frontend acceptance: `npm.cmd run validate` passed, platform tests passed (`19 passed`), production build passed with `--configLoader runner`, and `npm.cmd run smoke` passed after making the smoke harness use the same writable config-loader mode.
- CI/review state before final harness refinement: remote CI was initially blocked by a test-only asyncpg pool/event-loop issue; the fix is `3f77354`. PR #24 was created as a draft. Final CI/review state is recorded below after the corrected push.
- Final formal acceptance: the corrected branch was pushed to PR #24; the final pushed HEAD passed backend, frontend, and Docker CI. Thread-aware review fetch returned zero reviews, zero conversation comments, and zero review threads. Phase E is complete; Phase F is safe only after the normal product/release review decision, and no Phase F work was started.

## Phase F — campaign builder template integration

- Status: implementation slice complete on `feature/campaign-builder-template-integration`; no merge, deployment, or production access occurred.
- Migration: `20260713_0016_campaign_builder_integration` is additive after `20260713_0015`. It adds campaign `builder_config_json`, `snapshot_json`, `frozen_at`, and `finalized_at`, plus nullable `campaign_items.market_product_id`. Existing `CampaignItem.product_id` remains compatible. Downgrade removes only these additive columns and the new foreign key/index; frozen data created by the migration is not recoverable after downgrade without backup restore.

### Workflow and resolution rules

The builder now exposes `GET /api/campaigns/builder/options` with eligible published templates, active market products, and export limits. The market flow is details, template selection, market-product selection/order, content configuration, preview, and save/finalize. Draft and archived templates are excluded; template selection is validated again by the backend for ownership, publication, visibility, and plan eligibility.

Global, adopted, and custom templates continue to reference the exact `Template.id`; the row is the immutable version reference and there is no latest-version lookup at render time. A selected market product is validated against the current market and active state. Resolution keeps market overrides ahead of canonical values, with canonical image/name/category fallbacks and placeholder behavior; canonical `Product` rows are never mutated. Private products use `market_product_id` while legacy/global campaigns continue using `product_id`.

### Freeze and preview/export parity

Drafts resolve live. `POST /api/campaigns/{id}/finalize` validates the selected template and slot count, records the exact template version, ordered product identities, campaign values, locale/currency, and builder configuration in `snapshot_json`, then marks the campaign approved/frozen. Frozen campaigns reject destructive detail/item edits; a later revision should be a duplicate. Preview and export already share `render_campaign_preview_html`; `build_campaign_render_payload` is the single contract used to form the version-safe snapshot.

### Tests and acceptance

The isolated PostgreSQL 16 rehearsal passed: upgrade `0015 -> 0016`, downgrade, re-upgrade, `alembic current`, and `alembic heads` all completed with `20260713_0016` as the sole head. Focused PostgreSQL-backed campaign/template/rendering acceptance passed with `20 passed, 3 warnings`; the concurrent Telegram export regression also passed after preserving legacy campaigns without a template. The full CI run for final HEAD `369c65d` passed backend, frontend, and Docker validation. The local default Vite loader remains blocked by an existing Windows permission-protected `.vite-temp` path, while CI's clean build passes.

The deterministic Phase F browser harness and authenticated screenshots have not been run. PR #25 remains draft; review submissions and inline review threads are currently zero. No Phase F acceptance artifacts or formal completion are claimed.

### Phase G entry criteria

Run the deterministic Phase F seed and browser harness with the required authenticated screenshots, add end-to-end freeze/re-export and normalized preview/export parity assertions, certify the exact final CI run and review threads, and complete the remaining frontend wizard controls before declaring Phase G safe.
