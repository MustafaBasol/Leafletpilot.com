# Controlled Customer Signup and Platform Administration

Phase 20A adds a controlled signup lifecycle. Public visitors submit `#/start`; the API stores a `SignupRequest` only after consent and abuse checks. No `User`, `Market`, or `MarketUser` is created by the public endpoint.

## Roles and Boundaries

Platform Admins are stored in `platform_admins` and authenticate with `/api/platform/auth/login`. They use a separate JWT secret, token type, route prefix, frontend session key, and `sessionStorage`. A Platform Admin is not a tenant member and does not gain tenant access unless explicitly invited as a tenant user.

Market admins remain tenant users through `users` and `market_users`. Tenant JWTs are not accepted by platform routes; platform JWTs are not accepted by tenant routes.

## Environment

Set these values before enabling platform administration:

- `PLATFORM_ADMIN_ENABLED=true`
- `PLATFORM_JWT_SECRET`: strong non-placeholder value, at least 32 characters
- `PLATFORM_ACCESS_TOKEN_EXPIRE_MINUTES`
- `PUBLIC_SIGNUP_THROTTLE_SECRET`: strong non-placeholder value, at least 32 characters in production
- `PUBLIC_SIGNUP_THROTTLE_WINDOW_MINUTES`
- `PUBLIC_SIGNUP_THROTTLE_LIMIT`

No real secrets belong in committed env examples.

## Platform Admin Bootstrap

After migration:

```powershell
docker compose -f docker-compose.production.yml exec backend python -m scripts.create_platform_admin
```

For controlled automation, pass `PLATFORM_ADMIN_EMAIL`, `PLATFORM_ADMIN_FULL_NAME`, and `PLATFORM_ADMIN_PASSWORD` in the command environment. The script validates email, full name, and a 12 character minimum password, hashes the password through the existing security helper, and creates no market membership.

## Signup Statuses

`pending`, `reviewing`, `approved`, `rejected`, and `provisioned` are the stored states. Rejected requests require a reason. Provisioned requests are not casually reverted.

Rejected and unprovisioned requests are retained in this phase. Recommended retention is 180 days for rejected requests and 365 days for inactive unprovisioned requests, subject to legal and operational policy. No automatic deletion is implemented.

## Anti-Abuse

The public endpoint accepts a hidden honeypot field and returns the same generic accepted response for bot submissions and duplicate-looking rapid submissions. Throttling is database-backed via `signup_throttles`. The throttle key is an HMAC of client address plus email using `PUBLIC_SIGNUP_THROTTLE_SECRET`; raw client IP and forwarded headers are not logged or exposed.

## Provisioning

`POST /api/platform/signup-requests/{id}/provision` locks the signup request row, prevents rejected provisioning, creates a unique market slug, creates the market in `trial`, creates one `market_admin` invitation, stores only the invitation token hash, marks the request `provisioned`, and writes an audit event. The plaintext invitation URL is returned only in the successful provisioning response and is not stored.

If provisioning is replayed after success, the endpoint returns the existing market id without a new invitation URL.

## Market Lifecycle

Existing markets migrate to `active` and `completed` onboarding, so production tenants remain accessible. New provisioned markets start in `trial` with onboarding `not_started`.

Policy: suspended markets remain readable but tenant mutations are blocked through shared role dependencies. Archived markets are inactive and denied to tenant users.

## Tenant Onboarding

Market admins with incomplete onboarding are redirected to `#/onboarding`. Staff and viewers cannot update onboarding. The wizard persists profile, brand, template, and completion steps server-side. Product import and Telegram linking are shown only as later recommendations; they are not mandatory in this phase.

## Production Order

1. Add the new env variables and keep `PLATFORM_ADMIN_ENABLED=false`.
2. Rebuild and deploy the backend image.
3. Run `python -m alembic upgrade head`.
4. Set `PLATFORM_ADMIN_ENABLED=true` with a real `PLATFORM_JWT_SECRET`.
5. Run `python -m scripts.create_platform_admin`.
6. Rebuild and deploy the frontend.
7. Smoke test `#/start`, `/api/platform/auth/login`, platform provisioning, invitation acceptance, onboarding, dashboard, campaign creation, export, and Telegram webhook health.

## Rollback

The migration downgrade removes the new platform/signup/onboarding structures and added market columns. It intentionally does not delete unrelated tenant data. If any platform-created invitation exists without a tenant creator, downgrading may require retiring those invitations first because the previous schema required `created_by_user_id`.

## Known Limitations

No email delivery, billing, MFA, OAuth, AI workflow, image upload, Excel import, Telegram self-link, WhatsApp, or professional brochure redesign is included in this phase.
