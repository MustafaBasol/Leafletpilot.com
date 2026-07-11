# LeafletPilot Demo Readiness Audit

## Executive verdict

**Audited baseline:** `origin/main` at `4e7c20c` (`Merge pull request #14 from MustafaBasol/feature/pilot-customer-activation`).

**External-show decision:** **not yet safe for an unscripted customer demonstration.** The authenticated campaign-to-export backend path works, and Phase 20C invitation acceptance is well covered, but the product still exposes placeholder destinations, non-persistent settings, a simulated template preview, a two-template supermarket-only content set, and development-only demo records with placeholder image URLs. A tightly scripted internal demonstration is possible from an isolated, pre-seeded environment.

Production was not accessed. Production readiness is not claimed; a final authorized production read-only smoke test remains required after remediation.

## Evidence and environment

| Evidence | Result |
|---|---|
| Repository/code | Targeted CodeGraph queries from `src` and `backend/app`; route, API client, backend route, service, model, seed, migration, compose, and deployment-contract inspection |
| Production-like runtime | Separate Docker project `leafletpilot-audit`, isolated PostgreSQL and storage volumes, synthetic accounts, localhost-only intended ports |
| Browser | **Unavailable for application verification.** The in-app browser connected, but `127.0.0.1:18080` returned `ERR_CONNECTION_REFUSED`; Docker reported configured host bindings but no effective published ports |
| API/runtime | Internal container requests verified health, database, public signup, Platform Admin, invitation lifecycle, existing-user acceptance, session refresh, audit persistence, catalog/template/campaign reads, preview, export, history, and downloads |
| Frontend checks | `npm run validate`, `npm run test:platform` (12/12), `npm run build`, and `npm run smoke` passed |
| Backend checks | Full isolated-database suite: **129 passed, 1 skipped**, 4 deprecation warnings |
| Migrations | Clean upgrade through `20260710_0010`; one Alembic head |

Temporary audit-only disclosures:

- Added and later removed `docker-compose.audit.local.yml` to request ports 15432/18000/18080.
- Added and later removed two synthetic smoke scripts under `backend/scripts`.
- Used only synthetic `example.test` identities and isolated volumes.
- Raised `PUBLIC_SIGNUP_THROTTLE_LIMIT` from 3 to 20 only after reproducing a shared-IP throttle collision, so the rest of the lifecycle could be verified.
- Ran `seed_dev_data.py` with `ENVIRONMENT=development` against the isolated database, then exercised it through the production-configured backend. The seed correctly refused production mode.
- Invitation SMTP remained disabled; no email was sent and no real recipient was used.

## Status definitions

Each item has exactly one primary status. Precedence is: Broken, UI-only / placeholder, Partially functional, Functional but confusing, Not demo-ready, Fully functional, Not applicable.

| Status | Count |
|---|---:|
| Fully functional | 19 |
| Functional but confusing | 4 |
| Partially functional | 7 |
| UI-only / placeholder | 5 |
| Broken | 0 |
| Not demo-ready | 3 |
| Not applicable | 0 |
| **Total pages/features audited** | **38** |

## Complete audit matrix

| # | Area and exact route | Primary status | Evidence | Key result |
|---:|---|---|---|---|
| 1 | Landing `#/` | Fully functional | Code verified; build/smoke | Static marketing route renders and links to signup/login; claims still need a final visual review |
| 2 | Public signup `#/start` | Fully functional | API/runtime + tests | Persists signup request, consent, throttle row, and activity; returns neutral 202 response |
| 3 | Owner/customer login `#/login` | Fully functional | API/runtime + tests | Real JWT login and `/auth/me` work; invalid credentials are covered |
| 4 | Platform login `#/platform/login` | Fully functional | Tests + code | Loading, duplicate-submit guard, accessible labels, normalized errors, and session redirect exist |
| 5 | Invitation preview `#/accept-invitation?token=…`, `#/invite/:token` | Fully functional | API/runtime + tests | Valid token metadata and localized states are returned |
| 6 | New-user invitation acceptance | Fully functional | API/runtime + tests | Creates user and membership, marks token accepted, returns a usable session |
| 7 | Existing-user invitation acceptance | Fully functional | API/runtime + tests | Requires login and authenticated acceptance; returned session contained both markets |
| 8 | Invalid/expired/revoked/accepted states | Fully functional | API/runtime for invalid/revoked/accepted; tests for expired | Distinct statuses and HTTP errors exist; no browser claim |
| 9 | Session refresh and market selection after acceptance | Fully functional | API/runtime + code | Accepted membership appears immediately and selected-market logic runs |
| 10 | Platform overview `#/platform` | Fully functional | API/runtime + code | Counts and recent activity are backed by Platform APIs |
| 11 | Signup request list `#/platform/signup-requests` | Fully functional | API/runtime + code | Search/filter, loading, empty, and error states exist |
| 12 | Signup request detail/review/approve/reject `#/platform/signup-requests/:id` | Fully functional | API/runtime + tests | State transitions and guards work |
| 13 | Signup provisioning | Not demo-ready | API/runtime + code | Market and owner invitation are created, but disabled delivery returns no acceptance URL and is labeled failed; controlled synthetic SMTP is a demo prerequisite |
| 14 | Platform market list `#/platform/markets` | Fully functional | API/runtime + code | Lifecycle/readiness filters and empty/error states exist |
| 15 | Platform market detail/readiness `#/platform/markets/:id` | Fully functional | API/runtime + tests | Counts, blockers, onboarding, owner invitation, and recent activity are real |
| 16 | Platform lifecycle actions | Fully functional | Tests + code | Activate/suspend/archive guards, reasons, confirmation, and audit events exist |
| 17 | Platform owner invitation create/rotate/revoke | Not demo-ready | API/runtime + tests | State machine exists; disabled delivery is intentionally unavailable but is presented as a failed send and exposes no fallback token |
| 18 | Platform onboarding visibility | Fully functional | API/runtime + code | Status, step, readiness, and blockers are visible on market detail |
| 19 | Platform audit/activity history | Partially functional | API/runtime + code | `/platform/audit` and recent market activity exist, but there is no dedicated frontend audit route/page |
| 20 | Customer dashboard `#/dashboard` | Partially functional | Code verified | Campaign list is real; activity explicitly says real data is unavailable and several metrics are derived only from campaigns |
| 21 | Market/company setup `#/markets` | UI-only / placeholder | Code verified | Generic placeholder route is exposed in navigation; onboarding is the only real profile setup surface |
| 22 | Product management `#/products` | Partially functional | API/runtime + code | Real list/create/update/activate works; image/alias workflows and realistic image assets are not demo-complete |
| 23 | Brand management `#/brands` | Functional but confusing | API/runtime + code | Real list/create works; backend update/delete capability is not exposed |
| 24 | Category management `#/categories` | Functional but confusing | API/runtime + code | Real list/create works; backend update/delete capability is not exposed |
| 25 | Campaign list `#/campaigns` | Fully functional | API/runtime + code | Real market-scoped list, loading, empty, error, and permission-aware create action |
| 26 | New campaign wizard `#/campaigns/new` | Partially functional | API/runtime + code | Parse/create-from-text is real; “Save draft” is explicitly simulated and the wizard is not a true persisted step editor |
| 27 | Campaign detail/editor `#/campaigns/:id` | Partially functional | API/runtime + code | Real preview, matching, update, export, and downloads work; some editing/removal behavior remains mock-oriented or incomplete |
| 28 | Template list `#/templates` | Partially functional | API/runtime + code | Real list and active-state toggle; no UI creation or configuration editor despite backend POST/PATCH support |
| 29 | Template detail `#/templates/:id` | Partially functional | API/runtime + code | Loads real metadata/config, but “Create preview” is simulated and direct preview is not connected to real products/rendering |
| 30 | Campaign preview/export | Fully functional | API/runtime + tests | HTML preview generated; PDF 152,324 bytes and PNG 170,680 bytes completed and downloaded |
| 31 | Export history/status | Functional but confusing | API/runtime + code | Jobs/files persist on campaign detail; no usable global history/file center |
| 32 | Files/export center `#/files` | UI-only / placeholder | Code verified | Generic sample table and “next phase” empty state |
| 33 | Team/users `#/team` | Fully functional | API/runtime + tests | Member roles, invitations, one-time token link, revoke, and last-admin guard exist |
| 34 | Settings `#/settings` | UI-only / placeholder | Code verified | Entire screen uses local mock data; Save only sets a local message and does not persist |
| 35 | Bot connections `#/bot-connections` | UI-only / placeholder | Code verified | Explicitly states there is no real API call; Telegram backend webhook does not make this UI functional |
| 36 | Reports `#/reports` | UI-only / placeholder | Code verified | Generic placeholder route; no reporting backend route |
| 37 | Customer onboarding `#/onboarding` | Functional but confusing | Tests + code | Profile/brand/default template/complete APIs are real; raw field names and weak action error feedback reduce demo clarity |
| 38 | Responsive behavior | Not demo-ready | Repository/code only | CSS contains responsive rules, but no browser/device verification was possible; external demo must use a rehearsed desktop viewport |

## Runtime content baseline

The existing seed produced 9 visible products, 8 brands, 6 categories, 2 global templates, 1 draft campaign with 6 products, and no pre-existing exports. The two templates are `Premium Market` and `Compact Weekly`, both supermarket-oriented. Product images use `https://example.com/leafletpilot/demo/...`, so the data is structurally useful but not credible visual demo content.

The core backend journey succeeded after seeding:

1. Login to active, onboarding-complete demo market.
2. Load catalog, templates, and campaign.
3. Render a 5,969-byte HTML preview.
4. Create one PDF/PNG export job.
5. Observe `completed`, one attempt, no error.
6. List persisted files/history and download valid `application/pdf` and `image/png` payloads.

## Prioritized issue register

| ID | Priority | Route/page and expected vs actual | Files and backend references | Root cause and demo impact | Fix / size / work |
|---|---|---|---|---|---|
| DRA-001 | P0 | All customer routes need a repeatable clean tenant; only development seed exists and no reset command exists | `backend/scripts/seed_dev_data.py`, `backend/tests/test_seed_dev_data.py`; Market/Product/Template/Campaign models | Demo preparation is manual and cannot be safely repeated in a production-configured tenant | Add allow-listed demo fixture/reset with hard production/customer guards; **L**; backend, seed, tests, ops |
| DRA-002 | P0 | Products/preview/export should show real imagery; seed points to `example.com` placeholders | `backend/scripts/seed_dev_data.py`, ProductImage, preview/export services | Exports can complete with visually empty/broken products, immediately damaging credibility | Package licensed synthetic assets and validate availability before demo; **M**; assets, seed, backend |
| DRA-003 | P0 | `#/templates`, `#/templates/:id` should support a credible sector choice and real preview; only two market templates exist and direct preview is simulated | `src/pages/Templates.jsx`, `src/pages/TemplateDetail.jsx`, `backend/app/models/template.py`, preview renderer | Template selection is the center of the demo but offers no sector breadth or reliable direct preview | Build six-template pack and wire real preview; **L**; frontend, backend, seed, design |
| DRA-004 | P1 | Platform provisioning with intentionally disabled delivery should say “delivery disabled”; actual API/UI say failed and return no fallback link | `backend/app/services/invitation_email.py`, `backend/app/api/routes/platform.py`, `src/pages/platform/PlatformMarketDetail.jsx` | Configuration state is misrepresented as operational failure; operator trust drops | Add explicit disabled delivery state and controlled operator guidance; **M**; backend, frontend, tests |
| DRA-005 | P1 | Signup and invitation preview throttles should be independent; both increment the same IP bucket | `backend/app/api/routes/public.py`, `backend/app/api/routes/auth.py`, SignupThrottle | Two signup submissions plus previews reproduced 429 during a valid invitation audit | Namespace throttle purpose/key types and test cross-flow isolation; **S**; backend, tests, possible migration only if constraints require it |
| DRA-006 | P1 | `#/markets`, `#/files`, `#/reports` should work or stay out of demo navigation; all are generic placeholders | `src/routes/routes.js`, `src/pages/PlaceholderPage.jsx`, Sidebar | Presenter can click into openly unfinished screens | Hide behind capability flags or implement truthful empty states; **S**; frontend/design |
| DRA-007 | P1 | `#/settings` should persist market settings; actual screen is local mock state | `src/pages/Settings.jsx`, onboarding/market APIs | Saving appears successful but data is lost | Reuse market profile/brand APIs and reload persisted values; **M**; frontend/backend contract tests |
| DRA-008 | P1 | `#/bot-connections` exposes status/test actions; actual page explicitly has no API | `src/pages/BotConnections.jsx`, `src/data/mockData.js`, Telegram route | Unsupported actions can be mistaken for live integration | Remove from customer demo navigation or connect only truthful Telegram state; **S/M**; frontend/backend |
| DRA-009 | P1 | Dashboard should show real recent activity and catalog/export summary; actual activity is unavailable and metrics are campaign-derived | `src/pages/Dashboard.jsx`, ActivityLog/ExportJob/Product models | First post-login screen looks sparse and undercuts the story | Add market dashboard summary/activity endpoint or narrow claims; **M**; backend/frontend |
| DRA-010 | P1 | Platform audit should be reachable; backend `/platform/audit` has no frontend route | `backend/app/api/routes/platform.py`, `src/api/platformApi.js`, platform layout/routes | Valuable trust evidence is hidden | Add filtered audit page and navigation item; **M**; frontend |
| DRA-011 | P1 | `#/campaigns/new` “Save draft” should persist; actual action is simulated | `src/pages/NewCampaign.jsx`, campaign create/update endpoints | A presenter can trigger a false success message | Persist a draft or remove the action; **S/M**; frontend |
| DRA-012 | P1 | Template administration should create/edit reusable templates; frontend only toggles active state | Template pages/API/services/model | Operator cannot prepare the demo pack through the product | Add form/config editor with scoped/global permission rules; **L**; frontend/backend/design |
| DRA-013 | P2 | Product management should cover aliases and image quality; backend supports more than the UI | `src/pages/ProductCatalog.jsx`, catalog API/routes/models | Demo catalog maintenance looks shallow | Add alias and image management with quality feedback; **M**; frontend |
| DRA-014 | P2 | Export history should be discoverable globally; it only exists inside campaign detail while `#/files` is placeholder | Campaign detail, PlaceholderPage, campaign files/jobs endpoints | Presenter must know the exact campaign to find output history | Implement file center or remove route and use a labeled campaign-history path; **M**; frontend |
| DRA-015 | P2 | Onboarding/provision forms should use user-facing labels and action errors; raw field names are shown | `src/pages/Onboarding.jsx`, `src/pages/platform/SignupRequestDetail.jsx` | Technical labels and silent action failures look unfinished | Localize labels, add per-step loading/success/error and validation; **S**; frontend/design |
| DRA-016 | P2 | Unknown authenticated routes should show 404; actual fallback renders campaign placeholder | `src/App.jsx`, `src/pages/PlaceholderPage.jsx` | Broken links look like valid product pages | Add explicit not-found route; **XS**; frontend |
| DRA-017 | P2 | Customer app language should be coherent; invitation/platform support multiple locales while most customer pages are Turkish-only | Customer pages and platform i18n | Non-Turkish customer demos become inconsistent | Choose demo locale and complete customer i18n later; **L**; frontend/content |
| DRA-018 | P3 | Reporting should provide performance/matching/export metrics; route is placeholder | `src/routes/routes.js`, `src/pages/PlaceholderPage.jsx`; no backend report route | Useful future sales proof, not needed for the first happy path | Define reporting API and page after demo stabilization; **XL**; backend/frontend/design |
| DRA-019 | P3 | Full visual template editor is absent | Template model/service/pages and renderer | Limits long-term self-service but a curated pack is enough for first demo | Add schema-driven visual editor after curated pack; **XL**; product/design/frontend/backend |

Priority totals: **P0 3, P1 9, P2 5, P3 2 — 19 issues**.

## Top ten demo blockers

1. No production-safe, tenant-allow-listed demo fixture/reset workflow.
2. Placeholder `example.com` product imagery in rendered brochures.
3. Only two supermarket templates; no six-sector demo pack.
4. Direct template preview is simulated rather than renderer-backed.
5. Disabled owner-email delivery is shown as failed and exposes no fallback token.
6. Signup and invitation preview share an IP throttle bucket.
7. Placeholder Market, Files, and Reports destinations remain in navigation.
8. Settings displays false persistence.
9. Bot Connections exposes simulated status/actions.
10. Dashboard activity and several summary claims are not backed by real data.

## Recommended first implementation PR

Start with **Phase 20D-1: deterministic demo tenant and reset**. The runtime campaign/export path already works; reliable, realistic state is the highest-leverage blocker.

Expected files:

- Modify `backend/scripts/seed_dev_data.py` and `backend/tests/test_seed_dev_data.py` or extract shared fixture builders.
- Add `backend/scripts/seed_demo_tenant.py`, `backend/scripts/reset_demo_tenant.py`, and focused tests.
- Add packaged, license-safe demo product assets under a new documented demo asset directory and replace `example.com` URLs.
- Update `docs/demo/DEMO_DATA_STRATEGY.md` after implementation with the final operational commands.

Acceptance: one explicit allow-listed demo tenant can be created/reset idempotently; reset cannot target arbitrary or production customer tenants; six realistic products minimum have locally available images; one completed campaign/export exists after seed; a second reset yields the same counts and no cross-tenant changes.

## What to do next

```powershell
git switch main
git pull --ff-only origin main
git switch -c feature/demo-data-reset
```

Implement the Phase 20D-1 files above, then run:

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

After all Phase 20D remediation is deployed through the normal process, schedule a separately authorized production **read-only** smoke test. Do not seed, reset, rotate invitations, create exports, or mutate customer data during that final smoke.
