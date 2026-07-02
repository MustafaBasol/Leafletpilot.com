# Initial PostgreSQL Data Model

## Model Rules

- Use UUID primary keys for all persistent entities.
- Use `created_at` and `updated_at` on all mutable tables.
- Use `market_id` on every business object that belongs to a market.
- Use `Decimal`/PostgreSQL `numeric`, never float, for prices and money.
- Preserve raw incoming text on campaign items even after matching.
- Support both global catalog products and market-specific catalog products.
- Prefer soft archive fields such as `archived_at` for user-facing business data.

## Entity Summary

### User

Purpose: Human account for platform staff, market admins, market staff, and operators.

Key fields:

- `id`, `email`, `display_name`
- `password_hash` later; nullable in early mock-compatible setup
- `status` enum: `active`, `invited`, `disabled`
- `last_login_at`, `created_at`, `updated_at`

Relationships:

- Many `MarketUser` records.
- Creates campaigns, products, manual matches, and activity logs.

Indexes:

- Unique `email`.
- Index `status`.

MVP vs later:

- MVP can seed one demo user.
- Later add password reset, MFA, SSO, and invitation flow.

### Market

Purpose: Tenant boundary and customer profile.

Key fields:

- `id`, `name`, `legal_name`, `slug`
- `logo_file_id`, `primary_color`, `secondary_color`
- `address`, `phone`, `email`, `website`, `social_links` JSONB
- `default_template_id`, `currency`, `language`, `timezone`
- `subscription_plan`, `status`

Relationships:

- Has many products, campaigns, bot connections, settings, files, users.

Indexes:

- Unique `slug`.
- Index `status`.

MVP vs later:

- MVP supports multiple markets but one active market in the UI.
- Later add branches, billing, plan limits, and custom domains.

### MarketUser

Purpose: Joins users to markets and stores tenant role.

Key fields:

- `id`, `market_id`, `user_id`
- `role` enum: `platform_admin`, `market_admin`, `market_staff`, `operator`
- `status`, `created_at`

Relationships:

- Belongs to one user and one market.

Indexes:

- Unique `(market_id, user_id)`.
- Index `(user_id, role)`.
- Index `(market_id, role)`.

MVP vs later:

- MVP uses it for authorization checks.
- Later add invitations and per-module permissions.

### Brand

Purpose: Product brand registry.

Key fields:

- `id`, `market_id` nullable
- `name`, `normalized_name`, `logo_file_id`, `country`
- `status`

Relationships:

- Has many products.
- `market_id = null` means global brand.

Indexes:

- Unique `(market_id, normalized_name)`.
- Index `normalized_name`.

MVP vs later:

- MVP supports create/list/update.
- Later add merge tools and supplier brand imports.

### Category

Purpose: Product taxonomy and brochure grouping.

Key fields:

- `id`, `market_id` nullable
- `parent_id`, `name`, `normalized_name`
- `color`, `icon`, `sort_order`, `status`

Relationships:

- Parent/child categories.
- Has many products and campaign items.

Indexes:

- Unique `(market_id, normalized_name, parent_id)`.
- Index `(market_id, sort_order)`.

MVP vs later:

- MVP can use flat categories.
- Later add nested category management and template grouping rules.

### Product

Purpose: Catalog item used for matching and brochure rendering.

Key fields:

- `id`, `market_id` nullable
- `brand_id`, `category_id`
- `name`, `short_name`, `normalized_name`
- `barcode`, `package_size`, `package_type`
- `status` enum: `active`, `inactive`, `archived`
- `quality_score`, `notes`
- `last_used_at`, `usage_count`

Relationships:

- Has many aliases and images.
- Can be referenced by many campaign items.
- Global product when `market_id = null`; market-specific product when set.

Indexes:

- Index `(market_id, normalized_name)`.
- Index `barcode`.
- Index `(market_id, status)`.
- Index `(brand_id, category_id)`.

MVP vs later:

- MVP supports manual product CRUD and simple import later.
- Later add global-to-market overrides, supplier feeds, duplicate detection.

### ProductAlias

Purpose: Critical matching table for alternative product names.

Key fields:

- `id`, `market_id` nullable
- `product_id`
- `alias`, `normalized_alias`
- `source` enum: `manual`, `incoming_message`, `import`, `ai_suggested`
- `confidence`, `status`

Relationships:

- Belongs to product.

Indexes:

- Unique `(market_id, normalized_alias, product_id)`.
- Index `normalized_alias`.
- Index `(product_id, status)`.

MVP vs later:

- MVP stores manual aliases and aliases learned from manual matches.
- Later add alias approval queue and AI suggestions.

### ProductImage

Purpose: Stores image metadata for product rendering.

Key fields:

- `id`, `market_id` nullable
- `product_id`, `file_id`
- `image_type` enum: `primary`, `alternate`, `transparent_png`
- `quality_status` enum: `excellent`, `good`, `needs_review`, `missing`
- `width`, `height`, `background_removed`, `is_primary`

Relationships:

- Belongs to product and campaign file/object file.

Indexes:

- Index `(product_id, is_primary)`.
- Index `(market_id, quality_status)`.

MVP vs later:

- MVP stores uploaded PNG metadata.
- Later add background removal and quality checks.

### Template

Purpose: Brochure template metadata and supported output formats.

Key fields:

- `id`, `market_id` nullable
- `name`, `type`, `description`
- `supported_formats` JSONB
- `max_products_per_page`
- `preview_file_id`
- `template_key`, `version`
- `status`, `is_default`

Relationships:

- Campaigns reference selected template.
- Markets can reference default template.

Indexes:

- Index `(market_id, status)`.
- Unique `(market_id, template_key, version)`.

MVP vs later:

- MVP uses seeded templates.
- Later add template versioning and editor.

### Campaign

Purpose: Central workflow record for a brochure generation request.

Key fields:

- `id`, `market_id`, `template_id`
- `name`, `status`
- `source_channel` enum: `panel`, `telegram`, `whatsapp`
- `conversation_id`, `incoming_message_id`
- `campaign_date`, `date_range_text`
- `requested_formats` JSONB
- `approved_at`, `approved_by_user_id`
- `revision_count`, `last_error`

Relationships:

- Has many campaign items, files, export jobs, activity logs.
- Belongs to market and template.

Indexes:

- Index `(market_id, status, created_at)`.
- Index `(market_id, source_channel)`.
- Index `conversation_id`.

MVP vs later:

- MVP covers one market, one template, simple status flow.
- Later add duplication, archive, analytics, scheduling.

### CampaignItem

Purpose: One incoming product line inside a campaign.

Key fields:

- `id`, `market_id`, `campaign_id`
- `line_number`, `raw_text`, `incoming_name`, `normalized_incoming_name`
- `product_id` nullable
- `matched_product_name`, `match_status`
- `match_method` enum: `exact`, `alias`, `barcode`, `fuzzy`, `ai`, `manual`, `none`
- `match_score` numeric(5,2)
- `price_amount` numeric(12,2), `old_price_amount` numeric(12,2), `currency`
- `unit_label`, `quantity_text`, `notes`
- `use_without_image`, `excluded`

Relationships:

- Belongs to campaign.
- Optionally references product and category.
- Has many matching suggestions.

Indexes:

- Index `(campaign_id, line_number)`.
- Index `(market_id, match_status)`.
- Index `product_id`.

MVP vs later:

- MVP preserves raw text and selected match.
- Later add structured promotions like "2 al 1 ode".

### MatchingSuggestion

Purpose: Candidate matches generated for a campaign item.

Key fields:

- `id`, `market_id`, `campaign_item_id`, `product_id`
- `method`, `score`, `rank`
- `reasons` JSONB
- `status` enum: `suggested`, `accepted`, `rejected`

Relationships:

- Belongs to campaign item and product.

Indexes:

- Index `(campaign_item_id, rank)`.
- Index `(market_id, status)`.

MVP vs later:

- MVP stores top 3 candidates for manual review.
- Later add model version and feedback loop.

### CampaignFile

Purpose: Records uploaded, preview, and final generated files.

Key fields:

- `id`, `market_id`, `campaign_id`
- `file_type` enum: `original_upload`, `preview_png`, `brochure_pdf`, `brochure_png`, `instagram_post`, `instagram_story`, `whatsapp_image`
- `format` enum: `pdf`, `png`, `jpg`, `xlsx`, `csv`, `txt`
- `status` enum: `pending`, `processing`, `ready`, `failed`, `sent`, `archived`
- `storage_key`, `public_url` nullable, `signed_url_expires_at`
- `size_bytes`, `content_type`, `page_number`
- `created_at`, `sent_to_user_at`, `last_error`

Relationships:

- Belongs to campaign.
- May be referenced by product images or template previews through a generic file model later.

Indexes:

- Index `(campaign_id, file_type, status)`.
- Index `(market_id, created_at)`.
- Unique `storage_key`.

MVP vs later:

- MVP stores records and signed URL keys.
- Later add retention, virus scanning, CDN, and file versioning.

### ExportJob

Purpose: Tracks preview and final export work.

Key fields:

- `id`, `market_id`, `campaign_id`
- `job_type` enum: `preview`, `final_exports`, `send_files`
- `status` enum: `queued`, `running`, `succeeded`, `failed`, `cancelled`
- `requested_formats` JSONB
- `attempt_count`, `max_attempts`
- `started_at`, `finished_at`, `last_error`

Relationships:

- Belongs to campaign.
- Creates campaign files.

Indexes:

- Index `(status, created_at)`.
- Index `(campaign_id, job_type)`.

MVP vs later:

- MVP records jobs and can run synchronously.
- Later process through RQ/Celery.

### BotConnection

Purpose: Per-market messaging channel configuration and health.

Key fields:

- `id`, `market_id`
- `provider` enum: `telegram`, `whatsapp`
- `bot_name`, `phone_number`
- `status`, `webhook_status`
- `secret_ref` or encrypted token reference
- `last_message_at`, `connected_at`, `last_error`
- `settings` JSONB

Relationships:

- Has many conversations and incoming messages.

Indexes:

- Unique `(market_id, provider)`.
- Index `(provider, status)`.

MVP vs later:

- MVP implements Telegram only.
- Later add WhatsApp and provider-specific diagnostics.

### Conversation / MessageThread

Purpose: Channel-independent conversation state.

Key fields:

- `id`, `market_id`, `bot_connection_id`
- `provider`, `external_chat_id`
- `state`
- `active_campaign_id`
- `last_incoming_message_id`, `last_message_at`
- `metadata` JSONB

Relationships:

- Has many incoming messages.
- Can point to active campaign.

Indexes:

- Unique `(provider, external_chat_id)`.
- Index `(market_id, state)`.

MVP vs later:

- MVP supports one active campaign per chat.
- Later support multi-threaded interactions and handoff to operators.

### IncomingMessage

Purpose: Raw inbound message or file from Telegram/WhatsApp/panel paste.

Key fields:

- `id`, `market_id`, `conversation_id`, `bot_connection_id`
- `provider`, `external_message_id`, `sender_name`, `sender_external_id`
- `message_type` enum: `text`, `file`, `photo`, `callback`
- `text`, `file_id`, `payload` JSONB
- `received_at`, `processed_at`, `processing_status`, `last_error`

Relationships:

- Can create campaign.
- Belongs to conversation.

Indexes:

- Unique `(provider, external_message_id)`.
- Index `(market_id, received_at)`.
- Index `(processing_status, received_at)`.

MVP vs later:

- MVP processes text and stores files as placeholders.
- Later parse Excel/PDF and support richer callbacks.

### ActivityLog

Purpose: Audit trail and user-visible campaign timeline.

Key fields:

- `id`, `market_id`
- `entity_type`, `entity_id`
- `actor_user_id`, `actor_type` enum: `user`, `system`, `bot`, `operator`
- `action`, `message`, `metadata` JSONB
- `created_at`

Relationships:

- References campaigns, products, files, bot connections by polymorphic fields.

Indexes:

- Index `(market_id, created_at)`.
- Index `(entity_type, entity_id, created_at)`.

MVP vs later:

- MVP writes key campaign events.
- Later add advanced audit export and operator reporting.
