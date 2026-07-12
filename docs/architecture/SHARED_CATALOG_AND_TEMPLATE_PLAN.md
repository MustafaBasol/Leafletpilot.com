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
