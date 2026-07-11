# LeafletPilot Customer Demo Flow

## Phase 20D-2 readiness notes

- Platform Admin provisioning with `INVITATION_EMAIL_DELIVERY=disabled` is shown as **Manual delivery required**, never as a transport failure.
- An authenticated Platform Admin with the existing invitation permission can use **Copy invitation link**. The action rotates the effective invitation, returns the link once, and records an audit event without the token.
- SMTP transport/configuration errors remain **failed**. Expired, revoked, and accepted invitations never yield a usable manual link.
- Signup, invitation preview, and invitation acceptance use independent per-IP throttle namespaces.
- Template detail uses the real HTML renderer with deterministic products from the selected tenant; preview-only rendering does not create campaign, export, file, or history records.
- Pilot navigation exposes Dashboard, Products, Templates, Campaigns, Preview, Export, History/download, and Account/logout. Market, Files, Reports, Settings, and Bot Connections are hidden and direct access is guarded.

## Preconditions

- Use only the isolated demo tenant described in `DEMO_DATA_STRATEGY.md`.
- Rehearse on a desktop viewport; responsive behavior was not browser-verified in this audit.
- Confirm the demo market is active and onboarding-complete.
- Confirm at least 9 products, 2 or more templates, one draft campaign, and one completed PDF/PNG export are present.
- Open the exact routes below in separate tabs only if needed for fallback. Do not open Settings, Bot Connections, Reports, Market, or Files during the customer demo.
- Invitation SMTP is not part of this customer journey. If Platform Admin activation is shown separately, use controlled synthetic SMTP and verify its configured delivery state first.

## Recommended 7-minute journey

| Time | Exact page | User action | Expected visible result | Talking point | Fallback |
|---|---|---|---|---|---|
| 0:00–0:40 | `#/login` | Sign in as the isolated demo market admin | Redirect to `#/dashboard`; selected market appears in the shell | “Each customer works in a tenant-scoped market with role-based access.” | If login fails, use a pre-authenticated rehearsal tab; do not improvise credentials |
| 0:40–1:15 | `#/dashboard` | Point to campaign counts and recent campaigns; open the seeded campaign only after orienting the audience | Real campaign list and derived status metrics | “The dashboard focuses the team on campaigns requiring action.” | If dashboard data fails, go directly to `#/campaigns` and say the dashboard summary is unavailable |
| 1:15–2:00 | `#/products` | Search for one seeded product and open Add/Edit only if images and fields are rehearsed | Real product, brand, category, status, and image-quality data | “The catalog is reused across campaigns, improving speed and consistency.” | If images are missing, avoid opening image detail; explain that the catalog record drives matching and continue |
| 2:00–2:40 | `#/templates` | Select a known active template such as `Premium Market` | Real template metadata and supported output formats | “Templates turn the same product data into repeatable brand layouts.” | Do not click the simulated direct-preview action; return to the list and select the template from the campaign wizard |
| 2:40–3:50 | `#/campaigns/new` | Name the campaign, paste the rehearsed six-product list, parse it, review match results, select the template, and create | Real parse/matching summary, then redirect to the campaign detail | “LeafletPilot converts a promotion list into structured campaign items and flags exceptions.” | If parse/create fails, open the pre-seeded campaign at `#/campaigns/{seeded-id}`; do not use the simulated Save Draft action |
| 3:50–4:50 | `#/campaigns/{id}` | Show matched and missing-product sections; refresh the real HTML preview | Renderer-backed brochure preview with template name and generation time | “The team can resolve uncertain matches before generating customer-facing files.” | If the new campaign preview fails, use the pre-seeded campaign; if both fail, show the last completed PDF from campaign history |
| 4:50–5:50 | `#/campaigns/{id}` | Generate PDF and PNG | Export button shows progress; job completes and files appear | “One approved campaign produces channel-ready outputs from the same source.” | If rendering fails, show the persisted previous completed job and name the failure status honestly |
| 5:50–6:30 | Same campaign detail | Show export job status and download one PDF | Completed history row, ready file, non-empty download | “Every generation attempt and output remains traceable.” | If download fails, show status/file size and use a previously downloaded rehearsal copy |
| 6:30–7:00 | `#/team` (optional) | Show members and roles without creating an invitation | Real tenant members and permission roles | “Owners can delegate work without sharing credentials.” | Skip this step if time is short or the audience is focused on creative workflow |

## Optional Platform Admin prelude (2 minutes, not part of the core customer demo)

Only show this when the audience cares about onboarding operations.

1. Open `#/platform/login` and sign in with a synthetic platform operator.
2. Open `#/platform/signup-requests`, then one rehearsed request.
3. Show review/approval and market provisioning state without mutating it live.
4. Open `#/platform/markets/{id}` and explain readiness, onboarding, lifecycle, and recent activity.
5. Do not create or rotate an owner invitation unless controlled synthetic SMTP has already been tested. Disabled delivery is supported configuration, but the current UI labels it as failed and is not safe to demonstrate.

## Presenter guardrails

- Never imply `#/settings`, `#/bot-connections`, `#/reports`, `#/markets`, or `#/files` are working product areas.
- Never use the template detail “Create preview” control; it is simulated.
- Never use “Save draft” in the new campaign wizard; it is simulated.
- Do not demonstrate Telegram/WhatsApp connection management.
- Do not switch to another tenant unless both tenants contain synthetic data.
- If an operation fails, show the persisted status or fallback artifact; do not repeatedly click or refresh.

## Reset and rehearsal commands

Use an isolated database and storage directory with the four `DEMO_*` allow-list variables configured. Run `python -m app.scripts.demo_tenant inspect`, then `reset --confirm`, `seed`, `generate-exports`, and `verify`. Repeat `seed` and `verify` before the demo. A non-zero verification result is a stop condition.

## Acceptance rehearsal

The flow is accepted only when a fresh reset can complete login → products → templates → campaign → preview → PDF/PNG export → history/download twice consecutively without manual database edits. The second run must not create duplicate seed records or expose data from another market.
