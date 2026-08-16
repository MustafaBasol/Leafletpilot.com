# First Pilot Customer — Operational Runbook

Companion to [Pilot Customer Readiness](PILOT_CUSTOMER_READINESS.md) (Phase 28E). This is the operator-facing "what do I actually do" checklist. It intentionally points at existing detailed docs rather than duplicating them — those are the source of truth; this page is the sequence and the failure playbook.

## Onboard a customer

1. **Signup → provisioning → invitation** — follow the existing [Pilot Onboarding Checklist](../phase-20b-pilot-customer-operations.md#pilot-onboarding-checklist) steps 1–5 (receive signup, review, approve+provision, deliver invitation link, verify acceptance).
2. **Plan** — confirm the assigned plan (`starter`/`standard`/`pro`) matches what was sold; verify via `GET /api/market/plan` that the returned limits match `backend/app/services/plans.py`. Do not take the UI's word for it during the pilot — cross-check the registry once per new customer until this has a longer track record in production.
3. **Onboarding** — the owner completes brand/template/locale steps in the app. Support note: completion is currently a soft gate (not blocked on incomplete prior steps) — if a customer reports a confusing onboarding state, check `Market.onboarding_status` directly rather than assuming the UI enforced a strict order.
4. **Catalog import** — from Platform Admin, use the Phase 28D Excel preview-then-commit flow. Have the customer's product list ready in the documented template format (`GET /api/platform/markets/{id}/catalog-import/template`). Preview first, resolve any ambiguous/conflict rows explicitly, then commit. **If the customer's list needs updating later, re-running the same import is safe** — it will not create duplicates (verified in Phase 28E).
5. **Telegram binding** — link the owner's Telegram account per [Internal Telegram Bot MVP](../deployment/TELEGRAM_BOT_MVP.md). Confirm `/start` in the bot resolves to the correct market before handing off to the customer.
6. **First campaign** — walk the customer through one campaign end-to-end (Telegram message → matching → confirm → PDF/PNG) live on the call if possible. If any item comes back `match_status="not_found"`, that's expected for Telegram-originated campaigns until `generate-suggestions` is run — see [known behavior](#known-behavior-not-a-bug) below.
7. **Activate** — mark the market active/ready per the existing checklist step 8, and inspect the platform audit trail (step 9) as a final sanity check.

## Support: common failure modes

| Symptom | Likely cause | What to check |
|---|---|---|
| Invitation link not received | `INVITATION_EMAIL_DELIVERY=disabled`, or real SMTP misconfigured/rejecting | Check the invitation's delivery status via Platform Admin (fail-closed by design — a failed send creates a retryable failed invitation + audit entry, it does not pretend to have sent). Manually copy the one-time link as a fallback (documented flow, no code change needed). |
| Import row stuck as "conflict" or "ambiguous" and won't commit | Multiple already-adopted or structurally-duplicate global products exist for that name/package | This is safe-by-default behavior, not a bug — the system will never silently pick one. Resolve manually in Platform Admin by choosing the correct target, or flag for a Phase 28C-style catalog dedup pass if it's a systemic near-duplicate in the global catalog. |
| Telegram bot not responding | Webhook not reaching the backend, or bot not linked to the right chat | Confirm `TELEGRAM_BOT_ENABLED=true`, webhook URL is the exact configured HTTPS endpoint, and check backend logs for `telegram update failed` around the relevant timestamp (see [Phase 29 Production Smoke Test](../deployment/PHASE_29_PRODUCTION_SMOKE.md) step 9 for the exact log-grep command). |
| Telegram campaign has all "unresolved" products | Expected — Telegram-created campaigns don't run automatic matching (see below). Not a failure. | Open the campaign in the panel and run `generate-suggestions`, or confirm this is acceptable for this customer's workflow. |
| Export job failed / stuck | Playwright/Chromium render failure, or storage write failure | Run `python -m scripts.readiness_check` inside the backend container (see [Phase 29 Production Smoke Test](../deployment/PHASE_29_PRODUCTION_SMOKE.md) step 2) — it does a real render round-trip and will surface a Chromium or storage problem directly, not just "the endpoint returned 200". |
| Customer hits quota unexpectedly | Working as designed (10/month on Standard) — or a bug if it triggered below 10 | Query `Campaign` rows for that market with `status != 'cancelled'` directly; if the count is genuinely below the plan limit and still blocked, that's a real bug — escalate, don't just tell the customer to wait. |
| A 4th+ legitimate signup gets throttled/blocked in the same hour | `TRUSTED_PROXY_IPS` not configured for the real reverse-proxy topology — see [readiness report](PILOT_CUSTOMER_READINESS.md#14-envsecret-review) | Set `TRUSTED_PROXY_IPS` to the actual proxy's Docker network CIDR and restart the backend. |

## Known behavior (not a bug)

- Telegram-created campaigns skip automatic product matching (`generate_suggestions=False` on that path) and render straight from parsed text/price. This is pre-existing behavior, confirmed working-as-intended during Phase 28E, not something this phase changed.
- `complete_onboarding` does not hard-block on incomplete prior steps.
- The `global_ambiguous` import-match state always blocks and requires an explicit operator decision — this is deliberate safety behavior, not a stuck import.

## Rollback

Follow the existing [Update Flow](../deployment/PRODUCTION_DEPLOYMENT.md#update-flow) and [Restore](../deployment/PRODUCTION_DEPLOYMENT.md#restore) sections for the mechanics. Objective triggers for rolling back a deploy:

- Migration fails, or `alembic heads` shows more than one head.
- `/api/health`, `/api/health/db`, or `/api/health/readiness` fails to return 200 after the deploy's health-check grace period.
- Login is broken for an existing user.
- Any cross-tenant data leak is observed (treat as an immediate rollback + incident, not a "fix forward" candidate).
- Campaign creation or PDF/PNG export is broken for a real customer.
- Backend cannot reach persistent storage (verify with `python -m scripts.readiness_check` — the `storage` check specifically).

Do not "wait and see" against any of the above — application-image rollback is cheap (previous tag is retained per the existing deployment doc); database rollback is not automatic and requires the documented restore procedure, so prefer rolling back the application first and only reach for a database restore if the migration itself is the problem.

## Before this runbook can be used for a real deploy

See [Remaining blockers](PILOT_CUSTOMER_READINESS.md#remaining-blockers-before-go) in the readiness report — real SMTP, a real Telegram bot, and an actual production server all need to exist and be exercised at least once before this runbook's "Onboard a customer" section can be followed against a real paying customer.
