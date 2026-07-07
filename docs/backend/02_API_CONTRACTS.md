# MVP REST API Contracts

## General API Rules

- Base path: `/api/v1`
- IDs are UUID strings.
- Money values use string decimals, for example `"1.59"`.
- All market-scoped routes must validate the caller can access `marketId`.
- Responses should use ISO 8601 timestamps.
- Pagination: `?limit=50&cursor=...` for list endpoints.

Current implemented FastAPI routes use `/api` and temporary `X-Market-Id`
headers in several places until the older `/api/v1/markets/{marketId}` contract
is fully reconciled. Phase 18B adds a basic operational baseline: credentialed
CORS must use explicit origins, responses include simple security headers, and
real API failures should be shown visibly by the frontend instead of silently
falling back to mock data. `POST /api/campaigns/parse-text` and
`POST /api/campaigns/from-text` cap `raw_text` at 20,000 characters.
Phase 18C adds minimal real auth. For implemented `/api` routes,
`X-Market-Id` is now only the selected market id; catalog, campaign, template,
preview, export, and download routes require `Authorization: Bearer <token>`
and verify the authenticated user has an active `MarketUser` membership for
that market.
Phase 18D adds role authorization, market member endpoints, and invitation
onboarding. Login and `/auth/me` return each accessible market with `role`.

## Auth

### `POST /api/auth/login`

Purpose: Local MVP email/password login.

Request:

```json
{ "email": "demo@leafletpilot.com", "password": "demo1234" }
```

Response:

```json
{
  "access_token": "jwt",
  "token_type": "bearer",
  "user": { "id": "uuid", "email": "demo@leafletpilot.com", "full_name": "Demo Admin" },
  "markets": [{ "id": "uuid", "name": "Anadolu Market", "slug": "anadolu-market", "role": "market_admin" }]
}
```

Permissions: Public.

MVP/later: Add refresh tokens, password reset, automated invitation email,
safer token storage, and session revocation.

### `GET /api/auth/me`

Purpose: Load current user, roles, and market access.

Headers:

```text
Authorization: Bearer <token>
```

Response:

```json
{
  "user": { "id": "uuid", "email": "demo@leafletpilot.com", "full_name": "Demo Admin" },
  "markets": [{ "id": "uuid", "name": "Anadolu Market", "slug": "anadolu-market", "role": "market_admin" }]
}
```

Permissions: Authenticated.

### `POST /api/auth/accept-invitation`

Public invitation acceptance for a new user. Request:

```json
{ "token": "raw-token", "full_name": "Employee Name", "password": "strong-password" }
```

The token is hashed before lookup. Existing users are rejected with a conflict
and must log in first.

### `POST /api/auth/accept-invitation-authenticated`

Authenticated acceptance for an existing user. The logged-in user email must
match the invitation email. Request:

```json
{ "token": "raw-token" }
```

## Roles

- `market_admin`: full market access, team management, invitations, template
  mutation, operational catalog/campaign mutation, exports and downloads.
- `market_staff`: operational catalog/campaign mutation, exports, downloads and
  reads; no team, invitation, or template administration.
- `viewer`: reads, previews, and already generated downloads only.

Insufficient role returns 403 with a permission message. Missing or invalid auth
returns 401.

## Market Members And Invitations

All endpoints below are selected-market scoped through `X-Market-Id` and require
`market_admin`.

- `GET /api/market-members`: returns membership id, user id, email, full name,
  role, active flag, and creation time for the selected market.
- `PATCH /api/market-members/{membership_id}`: changes role and rejects
  unsupported roles or demoting the last active admin.
- `POST /api/market-invitations`: creates a pending invitation and returns the
  raw `invite_token` and `accept_url` once.
- `GET /api/market-invitations`: lists invitations without raw tokens or token
  hashes.
- `POST /api/market-invitations/{invitation_id}/revoke`: revokes only pending
  invitations from the selected market.

## Markets

### `GET /markets`

Purpose: List markets visible to the user.

Response:

```json
{ "items": [{ "id": "mkt_1", "name": "Anadolu Market", "location": "Albertville, France", "status": "active" }] }
```

Permissions: Platform admin sees all; market users see assigned markets.

### `GET /markets/{marketId}`

Purpose: Market profile and defaults.

Response:

```json
{
  "id": "mkt_1",
  "name": "Anadolu Market",
  "primaryColor": "#2563EB",
  "currency": "EUR",
  "language": "tr",
  "timezone": "Europe/Paris",
  "defaultTemplateId": "tpl_1",
  "defaultOutputFormats": ["a4_pdf", "a4_png", "instagram_post"]
}
```

Permissions: Market member or platform admin.

### `PATCH /markets/{marketId}`

Purpose: Update market profile/settings fields.

Request:

```json
{ "primaryColor": "#2563EB", "currency": "EUR", "defaultTemplateId": "tpl_1" }
```

Response:

```json
{ "id": "mkt_1", "updatedAt": "2026-07-02T10:00:00Z" }
```

Permissions: Market admin or platform admin.

## Dashboard

### `GET /markets/{marketId}/dashboard`

Purpose: Data for dashboard metrics, waiting approvals, missing products, and activity.

Response:

```json
{
  "metrics": {
    "campaignsThisMonth": 18,
    "waitingApproval": 5,
    "missingProducts": 11,
    "generatedFiles": 64
  },
  "waitingApprovals": [{ "id": "cmp_1", "name": "Hafta 28 Indirimleri", "waitingFor": "3h" }],
  "missingProducts": [{ "campaignId": "cmp_2", "incomingName": "Bizim Yag 5L", "suggestion": "Bizim Yag 5L" }],
  "activity": [{ "message": "Telegram botundan yeni urun listesi alindi.", "createdAt": "2026-07-02T09:30:00Z" }]
}
```

Permissions: Market member.

## Campaigns

### `GET /markets/{marketId}/campaigns`

Purpose: Campaign list with filters.

Query: `status`, `channel`, `templateId`, `hasMissingProducts`, `from`, `to`.

Response:

```json
{
  "items": [
    {
      "id": "cmp_1",
      "name": "Hafta 28 Indirimleri",
      "status": "waiting_approval",
      "productCount": 24,
      "missingCount": 2,
      "sourceChannel": "telegram",
      "templateName": "Premium Market",
      "updatedAt": "2026-07-02T12:20:00Z"
    }
  ]
}
```

Permissions: Market member.

### `POST /markets/{marketId}/campaigns`

Purpose: Create a campaign from panel input or pasted product list.

Request:

```json
{
  "name": "Hafta 28 Indirimleri",
  "templateId": "tpl_1",
  "campaignDate": "2026-07-05",
  "sourceChannel": "panel",
  "rawProductList": "Coca Cola 2L - 1.59\nEti Burcak - 0.99",
  "requestedFormats": ["a4_pdf", "a4_png", "instagram_post"]
}
```

Response:

```json
{ "id": "cmp_1", "status": "draft", "nextAction": "parse" }
```

Permissions: Market staff or higher.

MVP/later: MVP accepts raw text; Excel/PDF parsing later.

### `GET /markets/{marketId}/campaigns/{campaignId}`

Purpose: Campaign detail page.

Response:

```json
{
  "id": "cmp_1",
  "name": "Hafta 28 Indirimleri",
  "status": "missing_products",
  "template": { "id": "tpl_1", "name": "Premium Market" },
  "counts": { "items": 24, "matched": 22, "needsReview": 2 },
  "items": [],
  "files": [],
  "messages": [],
  "activity": []
}
```

Permissions: Market member.

### `PATCH /markets/{marketId}/campaigns/{campaignId}`

Purpose: Edit campaign metadata while not completed.

Request:

```json
{ "name": "Hafta 28 Market Firsatlari", "templateId": "tpl_2" }
```

Response:

```json
{ "id": "cmp_1", "status": "draft", "updatedAt": "2026-07-02T10:00:00Z" }
```

Permissions: Market staff or higher.

### `POST /markets/{marketId}/campaigns/{campaignId}/parse`

Purpose: Parse raw list into campaign items.

Request:

```json
{ "rawProductList": "Coca Cola 2L - 1.59\nEti Burcak - 0.99" }
```

Response:

```json
{ "campaignId": "cmp_1", "status": "matching", "createdItems": 2 }
```

Permissions: Market staff or operator.

### `POST /markets/{marketId}/campaigns/{campaignId}/match`

Purpose: Run matching service for campaign items.

Response:

```json
{ "campaignId": "cmp_1", "status": "missing_products", "matched": 1, "needsReview": 1 }
```

Permissions: Market staff or operator.

### `POST /markets/{marketId}/campaigns/{campaignId}/preview`

Purpose: Queue or run preview generation.

Request:

```json
{ "formats": ["preview_png"] }
```

Response:

```json
{ "campaignId": "cmp_1", "status": "preview_ready", "exportJobId": "job_1" }
```

Permissions: Market staff or operator.

MVP/later: MVP may create placeholder file records; real Playwright rendering later.

### `POST /markets/{marketId}/campaigns/{campaignId}/approve`

Purpose: Mark preview approved and queue final exports.

Request:

```json
{ "approved": true, "note": "Fiyatlar kontrol edildi." }
```

Response:

```json
{ "campaignId": "cmp_1", "status": "approved", "nextAction": "generate_final_files" }
```

Permissions: Market staff, market admin, or operator on behalf of customer.

### `POST /markets/{marketId}/campaigns/{campaignId}/request-revision`

Purpose: Save revision note and return campaign to editable state.

Request:

```json
{ "note": "Coca Cola fiyatini 1.49 yapin.", "requestedBy": "customer" }
```

Response:

```json
{ "campaignId": "cmp_1", "status": "revision_requested", "revisionCount": 1 }
```

Permissions: Market member or bot callback.

## Campaign Item Matching

### `PATCH /markets/{marketId}/campaign-items/{itemId}`

Purpose: Edit price, product match, or item behavior.

Request:

```json
{
  "productId": "prd_1",
  "priceAmount": "1.49",
  "matchStatus": "manual_selected",
  "useWithoutImage": false,
  "excluded": false
}
```

Response:

```json
{ "id": "itm_1", "matchStatus": "manual_selected", "matchScore": "100.00" }
```

Permissions: Market staff or operator.

### `GET /markets/{marketId}/campaign-items/{itemId}/suggestions`

Purpose: Show candidate product matches.

Response:

```json
{
  "items": [
    { "productId": "prd_1", "name": "Torku Sucuk 400g", "score": "82.00", "method": "fuzzy" }
  ]
}
```

Permissions: Market member.

## Products

### `GET /markets/{marketId}/products`

Purpose: Product catalog list and search.

Query: `q`, `brandId`, `categoryId`, `imageStatus`, `status`.

Response:

```json
{
  "items": [
    {
      "id": "prd_1",
      "name": "Coca-Cola 2L",
      "shortName": "Coca-Cola 2L",
      "brandName": "Coca-Cola",
      "categoryName": "Icecek",
      "barcode": "5449000000996",
      "imageStatus": "good",
      "status": "active",
      "usageCount": 48
    }
  ]
}
```

Permissions: Market member.

### `POST /markets/{marketId}/products`

Purpose: Create market-specific product.

Request:

```json
{
  "name": "Bizim Yag 5L",
  "shortName": "Bizim Yag",
  "brandId": "brd_1",
  "categoryId": "cat_1",
  "barcode": "8690572789015",
  "packageSize": "5L",
  "packageType": "Pet Sise",
  "aliases": ["Bizim Aycicek Yagi 5 Lt"]
}
```

Response:

```json
{ "id": "prd_1", "status": "active" }
```

Permissions: Market staff or higher; operators can create during concierge MVP.

### `PATCH /markets/{marketId}/products/{productId}`

Purpose: Update product fields and aliases.

Request:

```json
{ "shortName": "Bizim Yag 5L", "status": "active", "aliases": ["Bizim yag 5 litre"] }
```

Response:

```json
{ "id": "prd_1", "updatedAt": "2026-07-02T10:00:00Z" }
```

Permissions: Market staff or higher.

## Categories

### `GET /markets/{marketId}/categories`

Purpose: Category list.

Response:

```json
{ "items": [{ "id": "cat_1", "name": "Icecek", "sortOrder": 10, "status": "active" }] }
```

Permissions: Market member.

### `POST /markets/{marketId}/categories`

Request:

```json
{ "name": "Icecek", "color": "#2563EB", "sortOrder": 10 }
```

Response:

```json
{ "id": "cat_1", "status": "active" }
```

Permissions: Market admin or operator.

## Brands

### `GET /markets/{marketId}/brands`

Purpose: Brand list.

Response:

```json
{ "items": [{ "id": "brd_1", "name": "Coca-Cola", "productCount": 12, "status": "active" }] }
```

Permissions: Market member.

### `POST /markets/{marketId}/brands`

Request:

```json
{ "name": "Torku", "country": "TR" }
```

Response:

```json
{ "id": "brd_1", "status": "active" }
```

Permissions: Market admin or operator.

## Templates

Phase 15 implemented the local FastAPI template routes under `/api/templates`
using the temporary `X-Market-Id` market header, matching the current backend
route style rather than the older `/markets/{marketId}` planning paths below.
Implemented fields are `id`, `market_id`, `name`, `slug`, `description`,
`template_type`, `is_global`, `is_active`, `config_json`, `created_at`, and
`updated_at`. Global templates are visible to all markets; market templates are
visible only to the same market. Rendering, preview URLs, file generation, and
storage are not implemented.

Phase 16 adds deterministic campaign HTML preview rendering. Phase 17 adds
local PDF/PNG generation from the same HTML renderer.

### `GET /api/campaigns/{campaign_id}/preview-html`

Purpose: Render a campaign with its selected template into safe deterministic
HTML for browser preview.

Headers:

```text
X-Market-Id: <market-id>
```

Response:

```json
{
  "campaign_id": "cmp_uuid",
  "template_id": "tpl_uuid",
  "template_name": "Premium Market",
  "html": "<!doctype html>...",
  "generated_at": "2026-07-05T10:00:00Z"
}
```

Behavior:

- Uses `campaign.template_id` when available.
- Falls back to the active `premium-market` template when no template is set.
- Escapes user-generated text and does not execute template code.
- Supports `premium-market` and `compact-weekly` renderer styles.
- Does not write files or create export jobs; file generation is handled by the
  export-job endpoint.

### `GET /markets/{marketId}/templates`

Purpose: List global and market templates.

Response:

```json
{
  "items": [
    {
      "id": "tpl_1",
      "name": "Premium Market",
      "type": "premium",
      "supportedFormats": ["a4_pdf", "a4_png", "instagram_post"],
      "maxProductsPerPage": 18,
      "status": "active",
      "isDefault": true
    }
  ]
}
```

Permissions: Market member.

### `GET /markets/{marketId}/templates/{templateId}`

Purpose: Template detail.

Response:

```json
{
  "id": "tpl_1",
  "name": "Premium Market",
  "description": "Modern marketler icin temiz duzen.",
  "supportedFormats": ["a4_pdf", "a4_png", "instagram_post"],
  "maxProductsPerPage": 18,
  "previewUrl": "https://storage.example/signed-preview"
}
```

Permissions: Market member.

## Bot Connections

### `GET /markets/{marketId}/bot-connections`

Purpose: Show Telegram/WhatsApp connection health.

Response:

```json
{
  "items": [
    {
      "id": "bot_1",
      "provider": "telegram",
      "status": "ready",
      "botName": "@LeafletPilotBot",
      "webhookStatus": "healthy",
      "lastMessageAt": "2026-07-02T09:57:00Z"
    }
  ]
}
```

Permissions: Market admin or platform admin; staff can read status.

### `POST /markets/{marketId}/bot-connections/{provider}/test-message`

Purpose: Send a test message through configured provider.

Request:

```json
{ "text": "LeafletPilot test mesaji" }
```

Response:

```json
{ "status": "queued" }
```

Permissions: Market admin or platform admin.

MVP/later: Telegram only in MVP; WhatsApp later.

## Files And Export Jobs

Current implemented local API routes use `/api/campaigns` plus `X-Market-Id`
rather than the older planning path style below.

### `GET /api/campaigns/{campaignId}/files`

Purpose: List campaign uploads, previews, and final exports.

Response:

```json
{
  "items": [
    {
      "id": "file_1",
      "fileType": "preview_png",
      "format": "png",
      "status": "ready",
      "sizeBytes": 1800000,
      "storage_key": "markets/.../campaign.pdf"
    }
  ]
}
```

Headers: `X-Market-Id: <market-id>`.

Permissions: Temporary market header; real auth later.

### `POST /api/campaigns/{campaignId}/export-jobs`

Purpose: Generate local PDF/PNG files from deterministic HTML preview.

Request:

```json
{ "job_type": "final_export", "requested_formats": ["pdf", "png"], "status": "queued" }
```

Response:

```json
{
  "id": "job_uuid",
  "campaign_id": "campaign_uuid",
  "market_id": "market_uuid",
  "job_type": "final_export",
  "status": "completed",
  "requested_formats": ["pdf", "png"],
  "result_file_ids": ["file_uuid"],
  "error_message": null,
  "attempts": 1
}
```

Behavior:

- Requires `X-Market-Id`.
- Supports only `pdf` and `png`.
- Accepts at most two requested formats.
- Creates `CampaignFile` rows with `file_type=brochure_pdf` or
  `file_type=brochure_png`.
- Writes local files below `LOCAL_STORAGE_DIR`.
- Uses `running` as the current processing status because that is the existing
  database enum value; this maps to the planned `processing` concept.
- Runs synchronously for the MVP. Background workers and S3/R2 are deferred.

### `GET /api/campaigns/{campaignId}/files/{fileId}/download`

Purpose: Download a generated local campaign file.

Headers:

```text
X-Market-Id: <market-id>
```

Behavior:

- Verifies campaign and file belong to the header market.
- Resolves only stored relative `storage_key` values under `LOCAL_STORAGE_DIR`.
- Returns `application/pdf` for PDF and `image/png` for PNG.
- Returns `404` when the row is missing, cross-market, not ready, path-invalid,
  or the local file is missing.

### `GET /api/campaigns/{campaignId}/export-jobs`

Purpose: List export status for a campaign.

Response item:

```json
{ "id": "job_1", "status": "running", "attempts": 1, "result_file_ids": [] }
```

Permissions: Market member.

## Settings

### `GET /markets/{marketId}/settings`

Purpose: Market defaults and workflow settings.

Response:

```json
{
  "currency": "EUR",
  "language": "tr",
  "defaultOutputFormats": ["a4_pdf", "a4_png", "instagram_post"],
  "matching": { "autoMatchThreshold": "90.00", "reviewThreshold": "70.00" },
  "exports": { "previewApprovalRequired": true, "retentionDays": 180 }
}
```

Permissions: Market member.

### `PATCH /markets/{marketId}/settings`

Purpose: Update market-level settings.

Request:

```json
{
  "defaultOutputFormats": ["a4_pdf", "a4_png"],
  "matching": { "autoMatchThreshold": "90.00", "reviewThreshold": "70.00" }
}
```

Response:

```json
{ "marketId": "mkt_1", "updatedAt": "2026-07-02T10:00:00Z" }
```

Permissions: Market admin or platform admin.
