# Phase 20B Pilot Customer Operations

Phase 20B extends the Phase 20A platform foundation. It keeps PlatformAdmin authentication separate from tenant authentication and uses the existing signup request, market, onboarding, lifecycle, and invitation contracts.

## Signup Request State Machine

Signup requests use the existing statuses:

- `pending`: public request received.
- `reviewing`: a platform admin has claimed the request for review. This is the operational "under review" state.
- `approved`: the request is approved and eligible for provisioning.
- `rejected`: the request is closed with a required rejection reason.
- `provisioned`: a market and initial owner invitation were created.

Provisioned requests cannot be edited. Rejected requests cannot be reopened through the platform UI.

## Provisioning Transaction

Provisioning locks the signup request row, verifies it is approved, creates the market, initializes lifecycle and onboarding fields, creates the initial market owner invitation, links the signup request to the market, records platform audit events, and commits once. Repeated provisioning on an already provisioned request returns the existing market without creating another market or invitation.

## Slug Behavior

Requested slugs are normalized to lowercase hyphenated text. Explicit slug collisions return a conflict so an operator can choose a safe slug. Automatically generated slugs resolve collisions deterministically with numeric suffixes.

## Owner Invitation Lifecycle

Owner invitations use `MarketInvitation` with hashed tokens. Raw invitation URLs are returned only when the invitation is created or rotated. List/detail responses return only status, expiration, delivery mode, and acceptance/revocation timestamps. Email delivery is marked `manual`; no sent state is faked.

## Market Readiness

Readiness is derived, not persisted:

- `awaiting_owner`: no active market user yet.
- `onboarding`: owner exists but required setup is incomplete.
- `ready`: owner exists, onboarding is complete, and products exist.
- `suspended`: lifecycle is suspended.
- `blocked`: lifecycle is archived or another blocker prevents pilot use.

Blockers are returned with the market detail so operators can see why a market is not ready.

## Lifecycle Enforcement

Platform lifecycle actions support activate/resume, suspend, and archive. Suspension and archive require a reason; archive also requires explicit confirmation. Suspended and archived markets are marked inactive and tenant session construction rejects non-trial/non-active lifecycle states. Platform admins can still inspect those markets.

## Platform Audit Events

`platform_audit_logs` records platform admin actor ID, action, target type, target ID, timestamp, and safe metadata. Audit metadata must not include raw invitation tokens, JWTs, passwords, hashes, or full sensitive payloads.

Audited actions include signup review started, signup approved, signup rejected, market provisioned, owner invitation created, owner invitation rotated, owner invitation revoked, market suspended, market resumed, and market archived.

## Pilot Onboarding Checklist

1. Receive signup.
2. Review request and add review notes.
3. Approve and provision the market.
4. Copy the one-time owner invitation link and deliver it manually.
5. Verify invitation acceptance on the market detail page.
6. Monitor onboarding and readiness blockers.
7. Confirm market readiness.
8. Activate pilot access.
9. Inspect the platform audit trail.

## Rollback And Failure Behavior

Provisioning commits atomically. If market creation, invitation creation, or audit persistence fails before commit, the transaction rolls back and the signup request remains unprovisioned. Re-running provisioning after a successful commit is idempotent and returns the existing market reference without exposing a prior raw invitation token.
