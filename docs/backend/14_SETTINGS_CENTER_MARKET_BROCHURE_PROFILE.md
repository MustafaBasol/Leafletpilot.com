# Settings Center and Market Brochure Profile

## Scope

Market identity is maintained once, at the authenticated selected market. `markets.name`
remains the only market-name source of truth. The profile also stores address lines,
postal code, city, existing two-letter `country_code`, existing `contact_phone`, website,
Instagram, Facebook, and the existing market logo reference.

`GET /api/market/settings` is available to market members. `PATCH /api/market/settings`
requires `market_admin`; both endpoints derive the market solely from the authenticated
`X-Market-Id` membership context. They never accept a market id in the body or path.
Settings mutation logs include only market id, user id, and field names.

## Brochure visibility

The stable typed preferences are `brochure_show_logo`, `brochure_show_address`,
`brochure_show_phone`, `brochure_show_website`, `brochure_show_instagram`, and
`brochure_show_facebook`. The migration defaults logo to `true` and every optional
contact/social field to `false`. Existing markets therefore do not begin exposing
contact data after deployment.

Draft rendering projects the current enabled market profile with campaign data. The
market name is always rendered. Enabled contact and social values are compact footer
content; logo rendering reuses the existing `/api/market/logo` storage endpoints.

## Frozen campaigns and AI

Approval serializes the live render payload, including `market_profile`, into the normal
campaign snapshot before computing `snapshot_sha256`. The profile contains only enabled
brochure values and the frozen logo key. Approved preview, export, and automatic AI
professionalization consume that snapshot, so later settings changes do not affect an
approved campaign. Historical snapshots are not rewritten; snapshots without the new
profile continue to render and retain their existing frozen header identity.

Automatic AI professionalization builds immutable facts only from the frozen enabled
profile. Disabled fields are omitted. OCR validation requires every enabled text fact;
a changed or absent enabled fact rejects the professional candidate and leaves the
original approved output usable. Logo handling uses the frozen logo reference and the
existing fail-closed logo validation policy.

## Deployment

Apply `20260827_0034` with the new backend runtime after deploying the application
image. It is additive and has a single Alembic head. No environment variables or
production secrets are introduced.