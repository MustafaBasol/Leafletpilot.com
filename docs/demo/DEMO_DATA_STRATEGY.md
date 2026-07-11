# LeafletPilot Demo Data Strategy

## Recommendation

Use a **dedicated, production-isolated demo tenant** backed by deterministic fixture and reset commands. Do not reuse a real customer market, copy production records, or share one tenant between demo and customer workloads.

The current repository is not ready for that operational model:

- `backend/scripts/seed_dev_data.py` is idempotent and refuses `ENVIRONMENT=production`, which is correct for safety.
- It creates useful structural data, but only two supermarket templates, placeholder `example.com` image URLs, one draft campaign, and no completed exports.
- There is no reset script or tenant allow-list.
- The production Compose stack has persistent database/export volumes and correctly does not seed automatically.

Until Phase 20D-1 is implemented, use the existing seed only in a disposable isolated environment and destroy that environment after the audit/demo.

## Data ownership rules

### Permanent in the dedicated demo tenant

- One synthetic market with a conspicuous slug such as `leafletpilot-demo`.
- One market-admin presenter account and optional staff/viewer accounts using secret-manager credentials.
- Six curated sector templates and their licensed synthetic design assets.
- A stable catalog of synthetic brands, categories, products, aliases, and locally available product images.
- One completed “golden” campaign and one completed PDF/PNG export retained as fallback artifacts.
- A small, synthetic platform audit/activity history that demonstrates onboarding and export completion.

### Reset before each presentation

- Draft/rehearsal campaigns created during the previous presentation.
- Matching suggestions and manual resolutions attached to those campaigns.
- Export jobs/files other than the golden fallback artifacts.
- Pending/revoked invitations and throttle rows for the demo tenant's synthetic identities.
- Temporary team members and onboarding experiments.
- Mutable profile colors/default-template selections, restored to the known demo baseline.

### Never shared or copied

- Real customer users, emails, products, images, campaigns, exports, audit logs, tokens, or storage keys.
- Production SMTP credentials, JWT secrets, platform secrets, database snapshots, or object-storage credentials.
- Invitation links between tenants.
- A single demo password across production, staging, and local environments.
- Production database/storage volumes mounted into an audit container.

## Required implementation controls

The Phase 20D-1 seed/reset tooling must:

1. Require an explicit demo-data feature flag and a configured allow-listed market slug/ID.
2. Refuse to run when the target is absent, ambiguous, or not marked as a demo tenant.
3. Refuse wildcard deletion and never delete global/customer records by association.
4. Print the environment, database host, target market ID/slug, and planned row counts before mutation.
5. Require an explicit confirmation flag in non-development environments.
6. Be idempotent and covered by cross-tenant preservation tests.
7. Reset database records and stored export files consistently.
8. Generate no invitation for a real domain and send no email unless controlled synthetic SMTP is configured.
9. Verify the post-reset counts, golden campaign, template pack, image availability, and fallback exports.

## Controlled SMTP policy

- `INVITATION_EMAIL_DELIVERY=disabled` is a valid intentional configuration and must not be treated as a send attempt.
- For invitation demonstrations, use a synthetic SMTP inbox that cannot relay externally and addresses under a reserved synthetic domain.
- Verify delivery configuration before creating/rotating an invitation.
- Clear synthetic mailbox contents during reset.
- Never print full invitation tokens in CI logs or commit them to documentation.

The current API records disabled owner delivery as `failed`, reports “Invitation email delivery is not configured,” and provides no operator acceptance URL. This is a UI/API state-label issue, not evidence that SMTP itself is broken.

## Current disposable local procedure

This procedure is for local isolated use only. It is not a production demo reset.

Use a unique Compose project name and a synthetic environment file stored outside the repository, for example `C:\tmp\leafletpilot-audit.env`. The settings loader accepts either the JSON-array form used by `.env.production.example` or the comma-separated form documented in `backend/README.md`; use one form consistently and validate the resolved configuration before starting services.

Validate and start the isolated database:

```powershell
docker compose --env-file C:\tmp\leafletpilot-audit.env `
  -p leafletpilot-audit `
  -f docker-compose.production.yml `
  -f docker-compose.audit.local.yml config -q

docker compose --env-file C:\tmp\leafletpilot-audit.env `
  -p leafletpilot-audit `
  -f docker-compose.production.yml `
  -f docker-compose.audit.local.yml up -d postgres

docker compose --env-file C:\tmp\leafletpilot-audit.env `
  -p leafletpilot-audit `
  -f docker-compose.production.yml `
  -f docker-compose.audit.local.yml run --rm migration
```

Populate only the isolated database with the existing development fixture, then run the production-configured services:

```powershell
docker compose --env-file C:\tmp\leafletpilot-audit.env `
  -p leafletpilot-audit `
  -f docker-compose.production.yml `
  -f docker-compose.audit.local.yml up -d backend frontend

docker exec -e ENVIRONMENT=development `
  leafletpilot-audit-backend-1 `
  python scripts/seed_dev_data.py
```

Destroy only the isolated project after use:

```powershell
docker compose --env-file C:\tmp\leafletpilot-audit.env `
  -p leafletpilot-audit `
  -f docker-compose.production.yml `
  -f docker-compose.audit.local.yml down -v
```

`docker-compose.audit.local.yml` was a temporary untracked audit override and is not delivered by this PR. A future committed local-demo override may be added only after review; do not substitute the production project's name or environment file in these commands.

## Pre-demo checklist

- Confirm the target is the dedicated demo tenant and contains no real domain/email.
- Confirm migration head and health/database checks.
- Reset and reseed, then compare expected counts.
- Confirm all six templates are active and previewable.
- Confirm product image URLs/assets are reachable without public internet dependency.
- Generate and download one fresh PDF and PNG.
- Confirm one golden fallback export remains ready.
- Confirm dashboard, campaign, export history, and team pages load.
- Confirm placeholder routes are hidden or explicitly excluded from the script.
- Confirm SMTP is disabled for customer-flow demos or connected only to the synthetic inbox for invitation demos.
- Close any production tabs and do not use production credentials.

## Production comparison and remaining smoke

Repository inspection verified production settings validation, private PostgreSQL, persistent export storage, migration profile, non-root images, health checks, and production seed refusal. No production runtime was accessed. After remediation and normal deployment, a separately authorized read-only smoke must verify health, login, existing demo records, preview/export history visibility, and static asset availability without creating, resetting, inviting, exporting, or mutating any production data.
