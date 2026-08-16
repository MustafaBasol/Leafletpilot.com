# Phase 28E: Pilot Customer Readiness Report

**Baseline:** `origin/main` @ `98159cc5b63342ff824d3d987b1d41f2f72e18fe` (PR #66, Phase 28D Excel import merged).
**Branch:** `feature/pilot-e2e-production-readiness`.
**Scenario used:** synthetic "LeafletPilot Pilot Market" — FR / EUR / tr / Europe/Paris / Standard plan, Turkish brands (Ülker, Eti, Torku, Sütaş, Pınar) + Coca-Cola/Nutella, synthetic barcodes only.

## Final decision

**NO-GO for production deployment today.** The application code, once the fixes in this phase land, is in good shape — real auth/RBAC, real plan entitlements, a working import/export/Telegram pipeline, verified backups/restore, and a Docker Compose stack that actually starts and survives a recreate. The blockers are entirely **operational/infrastructure**, not code: nobody has verified real SMTP delivery, a real Telegram bot/webhook, or an actual production server in this environment. See [Remaining blockers](#remaining-blockers-before-go) below — they are the whole gap between this report and GO.

## What was validated, and how

All validation ran against disposable local infrastructure in this worktree: a throwaway PostgreSQL 16 container (`lfp-pilot-e2e-pg`), the real backend/frontend Docker images built from this branch, and an in-process ASGI test client (no live uvicorn server, no real network). Nothing here touched any real production system, real customer data, or real credentials.

### 1. Public signup → Platform Admin → provisioning → invitation → onboarding

New regression test: `backend/tests/test_pilot_e2e_phase28e.py::test_pilot_customer_full_journey_when_test_database_url_is_configured` (stages 1–5).

- Signup submission, listing, and approval work; repeat submissions each create a new pending row (anti-enumeration by design), correctly rate-limited.
- Provisioning produces a Market with correct plan (`standard`), lifecycle, trial expiry, and FR/EUR/tr/Europe/Paris locale; creates an owner invitation and a `platform_audit_logs` entry.
- Invitation acceptance is one-time-use (409 on reuse); the resulting user's role is scoped to exactly this market.
- Onboarding steps persist and reach `completed`. **Minor note:** `complete_onboarding` does not hard-block completion on incomplete prior steps (soft-gate only) — not a safety issue, just weaker UX guidance than the phase brief assumed.

### 2. Plan/entitlement enforcement (Phase 29A registry)

`GET /api/market/plan` matches `app/services/plans.py`'s Standard definition exactly: 10 campaigns/month, 250 private products, `pdf`+`png` export formats. Verified via direct comparison against the registry object, not a hand-copied expected value.

### 3. Catalog import (Phase 28D) — realistic 22-row workbook, and mandatory re-import idempotency

22-row synthetic XLSX: exact global matches, a strong/fuzzy match, new local products, a duplicate-in-file row, two invalid rows (missing name, invalid currency), decimal-comma EUR prices, package variants. All preview row states were asserted, global products were confirmed never mutated by the import, and the commit produced the correct local-product/audit records.

**Re-import of the identical file was explicitly re-verified**: 0 new local products created, previously-imported rows correctly recognized as `existing_market_product`, and `MarketProduct` row count identical before/after. This was the single most important correctness property in this phase and it holds.

One coverage gap found during review, not fixed: the matching service's `global_ambiguous` state (triggered by two structurally-identical unmerged global product candidates — see `app/services/catalog_matching.py:395-428`) is architecturally safe by code inspection (`finalize("global_ambiguous", "blocked", ...)` — always requires an explicit decision, never silently auto-adopts), but is not exercised by an explicit row in the new E2E test. **P3, recommend as a fast follow-up**, not a release blocker.

### 4. Manual product entry / duplicate prevention

`Ülker` vs `Ulker` with the same package is correctly blocked (409) by `_enforce_global_match_decision` unless the caller explicitly overrides.

### 5. Telegram ingestion, campaign creation, matching

Simulated via direct webhook POSTs with the correct `X-Telegram-Bot-Api-Secret-Token` header (no real bot token needed to validate this logic — see [Telegram production config](#telegram-production-configuration) for what real credentials would still need to verify). A realistic message list (Ülker Çokomel, Coca-Cola, Sütaş Ayran, Nutella with EUR prices) correctly created a campaign scoped to the right market with quota incremented exactly once.

**Real finding, fixed:** the campaign-creation Telegram handlers did not catch `HTTPException` from the campaign service, so a foreseeable condition (monthly quota exceeded) propagated as an unhandled exception — the webhook returned a non-200 to Telegram (triggering endless retries) and the user got a generic error instead of a clear quota message. Fixed in `backend/app/integrations/telegram/service.py` (see [Fixes](#fixes-made-this-phase)).

**Real (non-bug) finding, not fixed, worth a runbook note:** Telegram-created campaigns are created with `generate_suggestions=False` and go straight to export without ever running product matching — every item stays `match_status="not_found"` until an operator manually triggers `generate-suggestions`. Rendering itself works correctly from raw parsed text; catalog-linked benefits (images, canonical pricing) just don't apply automatically to bot-originated campaigns yet. This is pre-existing behavior, not introduced by this phase.

### 6. Campaign editing, templates, preview, PDF/PNG export, retry

- Price edits persist across reload.
- Standard plan correctly sees global templates; `/api/templates/custom` (Pro-exclusive) correctly 403s for Standard.
- Preview HTML round-trips Turkish characters (Ü, Ç, Ş, İ, ğ, ö) and EUR formatting without corruption.
- PDF export is a real Playwright render, verified by opening it with `pypdf` (valid page count). PNG export verified by opening it with PIL (valid dimensions).
- Export retry reuses the same completed job — no duplicate job, no extra quota consumption.

### 7. Quota enforcement — direct API and Telegram, both paths

10 campaigns succeed, the 11th is blocked with `403` and a readable error message via direct API. The identical attempt via the Telegram path is also blocked — **verified by querying the actual database row count** (`== 10`, not just checking response codes), closing the loop on whether either path could silently exceed quota.

### 8. Role authorization

A `viewer` role in the same market is correctly rejected (403) from campaign mutation, private-product creation, custom-template creation, and invitation management, while read access still works. Cross-token-type checks confirmed: a market user's token is rejected by Platform-only routes, and a Platform Admin token is rejected by market-only routes.

### 9. Tenant isolation — adversarial, direct API tampering

Extends the pre-existing `test_cross_market_isolation_across_resources_when_test_database_url_is_configured` coverage (campaigns, private products, custom templates) with export-file download, export-job listing, and Telegram binding hijack attempts across two markets. All correctly return 404/rejected; a forged Telegram callback referencing another market's ID never leaks that market's ID back to the attacker's chat.

### 10. Migrations

Single Alembic head (`20260816_0024`) confirmed via `alembic heads`. Clean `alembic upgrade head` from an empty disposable Postgres, independently verified twice (once directly, once inside the built production Docker image via the compose `migration` service).

### 11. Docker production build + real `up` smoke test

Not just `docker compose config` validation (which is all CI currently does) — an actual `docker compose -f docker-compose.production.yml up` was run against this branch's built images:

- `backend`/`frontend`/`postgres` all reached healthy state; `/api/health` and `/api/health/db` returned 200; frontend served its root page.
- **Restart persistence**: a marker row survived `docker compose restart postgres backend`.
- **Recreate persistence** (the stronger, more relevant test — this is what a real deploy does): `docker compose down` (without `-v`) followed by `docker compose up -d` — named volumes (`postgres_data`, `leafletpilot_storage`) survived, marker row still present, stack healthy again. **This directly answers the phase's stated release-blocker scenario ("a successful container restart that loses customer images") — it does not lose data.**

**Real bug found and fixed:** `INVITATION_EXPIRE_DAYS` and `SECURE_PROXY_HEADERS` are real `Settings` fields that were never forwarded in `docker-compose.production.yml`'s backend/migration environment blocks — an operator setting either in their env file would have had it silently ignored. Fixed.

### 12. Backup and restore — actually verified, not just documented

- `deploy/backup/postgres_backup.sh` and `storage_backup.sh` **do not work as written** against the bundled `docker-compose.production.yml` topology, because `postgres` has no published host port and storage is a named Docker volume, not a host bind mount by default. This was a real, confirmed gap between the documented backup procedure and the actual shipped topology.
- A working alternative (`docker compose exec`/helper-container based) was used to take a real `pg_dump --format=custom` backup of seeded test data, and **that backup was restored into a fresh, separate disposable Postgres via `pg_restore --no-owner`, with matching table and row counts confirmed.** This is real, evidence-based restore verification, not a documentation-only claim.
- `docs/deployment/PRODUCTION_DEPLOYMENT.md` now documents the commands that actually work against the shipped topology, with the original host-path forms kept as the documented alternative for anyone using a host bind mount instead.
- **P2, not fixed this phase:** the backup shell scripts themselves should ideally be updated to default to the `docker compose exec` form so a future operator following the script (not the doc prose) doesn't hit the same gap. Left as a fast-follow since the doc fix gives a complete, verified working procedure today.

### 13. Frontend

`npm ci`, `npm run validate`, `npm run build`, `npm run smoke` all green. `npm audit` shows 2 high-severity advisories in transitive Vite dev-tooling dependencies (`nanoid`, `postcss`) — not shipped in the production runtime bundle. P3 hygiene item, not a blocker.

### 14. Env/secret review

No real secrets found anywhere in example files. One real, confirmed **P1** finding: `TRUSTED_PROXY_IPS` is left blank in the shipped example, but the public-signup IP throttle only trusts `X-Forwarded-For` from peers listed there. Behind the documented Traefik topology (proxy on the same Docker network), every request appears to originate from Traefik's own container IP, so **distinct real users share one throttle bucket and the 4th+ legitimate signup within the window gets wrongly blocked.** Documented with the fix (set to the proxy's network CIDR) in both `.env.production.example` files. This must be set correctly at actual deploy time — it cannot be verified further without a real reverse-proxy topology to test against.

### 15. Auth/JWT/security spot review (read-only, this session)

- Hand-rolled JWT (HS256-only, enforced server-side regardless of the token's own header — prevents algorithm-confusion attacks), constant-time signature comparison, PBKDF2-SHA256 password hashing at 390,000 iterations. No new vulnerability found.
- No token/password values found in any logging call.
- Excel import: 10MB upload cap, 3000-row cap, content-type restricted to `.xlsx`, filename truncated to 255 chars, formulas never evaluated (`openpyxl` `data_only=False` — no formula execution risk).
- No server-side fetch of user-supplied URLs anywhere in `app/` — no SSRF vector for "image URL" style input.

## Fixes made this phase

| File | Fix | Severity |
|---|---|---|
| `backend/app/core/config.py` | `BACKEND_CORS_ORIGINS`/`TRUSTED_HOSTS`/`TRUSTED_PROXY_IPS` now `Annotated[list[str], NoDecode]` — pydantic-settings 2.15's own JSON auto-decode was crashing `Settings()` construction on blank/plain-string values *before* the app's existing custom parser could run. `TRUSTED_PROXY_IPS=` (blank) is exactly what `docker-compose.production.yml` always injects by default — **this was a genuine "backend container never starts" production blocker**, now fixed. | **P1** |
| `backend/app/integrations/telegram/service.py` | Campaign-creation handlers now catch `HTTPException` (e.g. quota exceeded) and send a readable Telegram message instead of propagating an unhandled exception that made the webhook return non-200 to Telegram. | **P1** |
| `docker-compose.production.yml` | Forward previously-dropped `INVITATION_EXPIRE_DAYS`/`SECURE_PROXY_HEADERS` env vars to the backend/migration services. | P1 |
| `.env.production.example`, `backend/.env.production.example` | Document the `TRUSTED_PROXY_IPS` signup-throttle risk; document previously-undocumented `INVITATION_EXPIRE_DAYS`. | P1 (doc) |
| `backend/.env.example` | `BACKEND_CORS_ORIGINS=http://localhost:5173` → `["http://localhost:5173"]` (plain form crashes fresh local dev setup even after the config.py fix, since it's still ambiguous vs. JSON array syntax at the doc level). | P2 (doc) |
| `docs/deployment/PRODUCTION_DEPLOYMENT.md` | Corrected backup/restore commands for the actual (no-host-port, named-volume) topology; documented the verified end-to-end restore test. | P1 (doc) |
| `backend/tests/test_pilot_e2e_phase28e.py` | New, 1008 lines, 4 test functions — durable regression coverage for the full pilot journey, quota enforcement (both paths), role authorization, and extended tenant isolation. | new coverage |

Every fix above is covered by the new/existing regression suite; nothing was fixed by weakening an assertion.

## Test results

- Backend: **557 passed, 2 failed, 2 skipped** (`cd backend && ./.venv/Scripts/python.exe -m pytest -q`, against the disposable Postgres, `TEST_DATABASE_URL` configured).
- The 2 failures are a confirmed Windows `MAX_PATH` (260-character) artifact from `pytest`'s own `tmp_path` fixture combined with this repo's deeply-nested worktree path (`.claude/worktrees/pilot-e2e-production-readiness/...`) — independently verified by measuring the failing paths (267 and 287 characters). **Not reproducible on Linux** (production containers and GitHub Actions `ubuntu-latest` CI both have no such limit), and not a product bug. Do not "fix" by shortening product code paths.
- Alembic: single head, clean upgrade from empty DB, verified twice independently.
- Frontend: `npm run validate && npm run build && npm run smoke` all green.
- Docker: both images build; full `docker compose -f docker-compose.production.yml up` reaches healthy; survives restart and full recreate without data loss.

## Remaining blockers before GO

These require real infrastructure/credentials that are not available in this development sandbox. They are the entire remaining gap to GO — see [Runbook](FIRST_CUSTOMER_RUNBOOK.md) for the exact operator steps to close each one.

1. **Real SMTP delivery** — `INVITATION_EMAIL_DELIVERY=smtp` has never been exercised against a real mail provider in this phase. The code path, config validation, and fail-closed behavior on delivery failure are all verified by unit/integration tests, but nobody has watched a real invitation email land in a real inbox.
2. **Real Telegram bot/webhook** — the webhook ingestion, matching, quota, and tenant-isolation logic are all verified via simulated `POST` requests carrying the correct secret header. Nobody has registered a real bot with Telegram, pointed its webhook at a real HTTPS endpoint, and sent a real message from a real Telegram client.
3. **Real production server** — no actual VPS/host exists yet for this pilot. DNS, HTTPS/TLS termination, and the Traefik reverse-proxy topology (which directly determines whether the `TRUSTED_PROXY_IPS` fix above is configured correctly) have not been exercised against a real network path.
4. **`TRUSTED_PROXY_IPS` must be set correctly at deploy time** — this is now documented, but its correctness can only be confirmed against the real reverse-proxy topology once one exists.

## Operating constraints for the pilot once GO is reached

- Telegram-created campaigns need a manual `generate-suggestions` step by an operator before catalog-linked pricing/images apply — flag this to the pilot's first support contact.
- The `global_ambiguous` catalog-match path is safe (blocks by default) but not covered by an explicit automated test — treat any operator report of an unexpected import block on a near-duplicate global product as expected behavior, not a bug, pending the P3 follow-up test.
- Backup restore has been verified through the `docker compose exec`/helper-container procedure now documented in `PRODUCTION_DEPLOYMENT.md` — do not use the raw `deploy/backup/*.sh` scripts unqualified against the shipped Compose topology; they assume a directly-reachable Postgres/host storage path that this topology does not have.
