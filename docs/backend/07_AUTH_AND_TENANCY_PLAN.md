# Auth And Tenancy Plan

## Goal

Prepare LeafletPilot for real customers without overbuilding auth in the MVP. The backend should enforce market scoping from the first database migration, even while the frontend still uses mock local auth.

## Phase 18C Implemented Baseline

Phase 18C replaces the unsafe `X-Market-Id`-only demo access with minimal real
auth:

- `POST /api/auth/login` accepts email/password and returns a Bearer access token.
- `GET /api/auth/me` returns the current user and active markets.
- Seed creates `demo@leafletpilot.com` with local-only password `demo1234`.
- `/api/catalog/*`, `/api/campaigns/*`, and `/api/templates/*` require a token.
- The frontend stores the token and first returned market in `localStorage` for the local MVP.
- `X-Market-Id` remains as the selected market header, but backend dependencies verify active `MarketUser` membership before allowing access.
- Health endpoints remain public.

Remaining hardening: httpOnly cookie or safer token strategy, refresh tokens,
full role matrix, password reset, invitation/onboarding flow, audit coverage,
and deployment-grade secret management.

## Phase 18D Implemented Baseline

- Central roles are `market_admin`, `market_staff`, and `viewer`.
- Backend dependencies load the current `MarketUser` membership from the
  database and enforce role checks centrally.
- Read routes allow all roles; campaign/catalog mutations and export creation
  allow admin/staff; template mutations and team/invitation administration are
  admin-only.
- Login and `/auth/me` include market role data. The frontend market switcher
  only allows markets returned by the backend session.
- Admins can list members, change roles, and create/revoke manually shared
  invitation links.
- Invitation tokens are generated with a secure random token, stored hashed, and
  returned only on creation. Accepted, revoked, and expired invitations cannot
  be reused.

Remaining production limits: access token in `localStorage`, no refresh token,
no password reset, no automated invitation email, no MFA, no production audit
trail for team changes, and production secret rotation is still required.

## Role Model

### Market Admin

Scope: One or more assigned markets.

Can:

- Manage own market settings.
- Manage products, categories, brands, and aliases for own market.
- Create and approve campaigns.
- View bot connection status.
- Manage market staff later.

MVP:

- Main customer role.

### Market Staff

Scope: Assigned market.

Can:

- Create campaigns.
- Edit campaign items.
- Approve previews if allowed by market policy.
- Add limited products and aliases.

MVP:

- Useful for employees who send product lists or review previews.

### Viewer

Scope: Assigned market.

Can:

- Read campaigns, catalog, and templates.
- View previews and download already generated files.

Cannot mutate records, generate new exports, or manage team access.
- Create product aliases.
- Regenerate previews and files.
- Mark customer approval based on bot/customer communication.

MVP:

- Important for concierge operation during pilot customers.

## Market Scoping

Rules:

- Every market-owned business table has `market_id`.
- API routes include `marketId` for market-scoped resources.
- Queries must filter by `market_id` unless caller is platform admin and endpoint explicitly supports cross-market access.
- Product, brand, category, and template can be global with `market_id = null`.
- Market-specific records should override global records only through explicit service logic.

Examples:

- A market user cannot access another market's campaign by changing URL IDs.
- A campaign item must have the same `market_id` as its campaign.
- A product linked to a campaign item must be global or belong to the campaign market.

## Frontend Mock Auth Replacement

Current frontend stores local mock auth. Backend phases should replace this gradually:

1. Keep frontend mock flow working during backend scaffold.
2. Add `/auth/mock-login` and `/auth/me` so frontend can shift to API-backed identity without real passwords.
3. Add real users and sessions after core data model is stable.
4. Remove local-only auth once the API integration phase starts.

Why replace it:

- Local storage does not prove identity.
- Market scoping needs a trusted backend user.
- Bot approval and operator actions need auditability.
- Real customers need password reset and account disable controls.

## Subscription Readiness

Do not implement billing in MVP, but keep fields ready:

Market fields:

- `subscription_plan`
- `subscription_status`
- `trial_ends_at`
- `monthly_campaign_limit`
- `monthly_export_limit`

Usage events later:

- campaign created
- final export generated
- Telegram campaign completed
- storage consumed

MVP:

- Store plan-like fields only if they help operations.
- Do not block product workflows based on billing.

## Permission Notes By Module

| Module | Read | Write |
|---|---|---|
| Dashboard | Market member | No direct writes |
| Campaigns | Market member | Market staff, admin, operator |
| Product catalog | Market member | Market staff limited, admin, operator |
| Categories/brands | Market member | Market admin, operator |
| Templates | Market member | Platform admin; market admin can choose defaults |
| Bot connections | Market staff read status | Market admin, platform admin |
| Files | Market member | System, operator |
| Settings | Market member | Market admin, platform admin |

## MVP Auth Guardrails

- Do not expose cross-market list endpoints to normal market users.
- Do not let client-provided `marketId` override authenticated access.
- Log actor and market for campaign approvals and manual matches.
- Keep provider tokens out of API responses.
