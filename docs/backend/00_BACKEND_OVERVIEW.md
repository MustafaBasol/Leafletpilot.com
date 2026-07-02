# LeafletPilot Backend Overview

## Purpose

The Phase 4 backend plan prepares LeafletPilot for a real backend without changing the current frontend-only demo. The backend should support a narrow MVP first: products, campaigns, matching, Telegram intake, previews, approvals, and generated files.

Recommended stack:

- API: Python FastAPI
- Database: PostgreSQL
- ORM: SQLAlchemy or SQLModel
- Migrations: Alembic
- File storage: S3-compatible object storage
- Jobs: simple internal worker first; RQ or Celery later
- First messaging channel: Telegram
- Later messaging channel: WhatsApp Business API
- Later exports: HTML/CSS templates rendered through Playwright
- Later AI: parsing and matching assistance behind a service boundary

## Main Backend Modules

| Module | MVP responsibility | Later responsibility |
|---|---|---|
| `api` | FastAPI routers, request validation, response schemas | Versioned APIs and public webhooks |
| `auth` | Mock-compatible user identity and role checks | Real login, password reset, SSO, billing gates |
| `tenancy` | Market scoping for all business records | Subscription limits, branches, per-market quotas |
| `catalog` | Products, brands, categories, aliases, images | Bulk import, image quality automation, supplier feeds |
| `campaigns` | Campaigns, campaign items, statuses, approvals | Advanced revisions, analytics, duplication |
| `matching` | Exact, alias, barcode, fuzzy scoring | AI-assisted normalization and learning loops |
| `templates` | Template metadata and supported formats | Template editor, versioning, rendering rules |
| `files` | Upload records, generated file records, signed URLs | Retention policies, virus scanning, CDN |
| `messaging` | Telegram webhook intake and outgoing messages | WhatsApp provider and channel abstraction |
| `jobs` | Parse, match, preview, export job records | Dedicated queue workers and retries |
| `activity` | Audit and activity timeline entries | Reporting, operator metrics, notifications |
| `settings` | Market preferences and output defaults | Plan-based settings and feature flags |

## Service Boundaries

Keep boundaries simple in the MVP:

- API handlers should validate input, check tenant access, and call services.
- Services should own workflow decisions such as campaign transitions and matching outcomes.
- Database models should be persistence-only and not contain business workflow logic.
- Messaging providers should translate external channel payloads into internal `IncomingMessage` records.
- Export generation should be invoked through jobs, even if the first worker runs in-process.

The first backend can be one deployable FastAPI app. Do not split into microservices until volume or operational needs require it.

## Why Telegram First

Telegram is the lowest-friction MVP channel:

- Bot creation is fast through BotFather.
- Webhook payloads are straightforward.
- File and image sending are simpler than WhatsApp Business API.
- Inline buttons support preview approval and revision actions.
- There is no business account approval process before pilot testing.

Telegram lets the product validate the core promise before investing in heavier messaging compliance.

## Why WhatsApp Later

WhatsApp is important for the target customers, but it should follow Telegram because:

- WhatsApp Business API setup requires business verification, phone number setup, templates, and provider decisions.
- Message templates and session windows affect UX design.
- Operational errors are harder to debug during early product discovery.
- The backend should first prove campaign creation, product matching, approvals, and file delivery.

Design the messaging layer with a provider abstraction from the start, but implement only Telegram in the MVP.

## Why AI Is Not the Layout Engine

AI should assist with parsing and matching, not final brochure layout.

AI can help with:

- Normalizing noisy product names.
- Suggesting category and brand.
- Choosing between ambiguous matching candidates.
- Shortening long product names for approved fields.
- Reporting missing fields.

AI should not generate final layout because LeafletPilot needs:

- Repeatable professional templates.
- Predictable PDF and PNG output.
- Price and product accuracy.
- Template capacity rules.
- Customer approval before final files.

The layout engine should be deterministic: template metadata plus campaign data produces a controlled preview/export.

## MVP Backend Priorities

1. Create a stable tenant-aware data model.
2. Persist products, aliases, campaigns, campaign items, templates, bot connections, files, messages, and activity logs.
3. Expose REST APIs that match the current frontend screens.
4. Implement deterministic product matching before AI.
5. Add Telegram webhook intake after core APIs are stable.
6. Record export jobs and files before implementing real PDF/PNG generation.
7. Preserve approval and revision history.

## Non-Goals For The Next Backend Phase

- No WhatsApp Business API implementation.
- No AI provider integration.
- No PDF/PNG rendering.
- No Docker/deployment setup unless Phase 13 starts.
- No payment or subscription enforcement.
- No production-grade authentication beyond preparing the model and API boundary.
