# AI-2 Provider-Neutral Revision Orchestration

AI-2 is a bounded natural-language **intent parser**. It does not design a
brochure, mutate campaign rows, or own persistence. The deterministic AI-1
revision service remains the only authority that can apply brochure-draft
changes.

## Flow

```text
Panel
  ↓  POST /api/campaigns/{campaign_id}/revision-intent
AI Revision Proposal API
  ↓
Capability Router (cheap_text_revision | complex_text_revision)
  ↓
Provider-neutral AIProvider
  ↓
Strict Pydantic parse + semantic/tenant/protected-fact validation
  ↓
Tenant-scoped Proposal Store
  ↓  explicit user confirmation
POST /api/campaigns/{campaign_id}/revision-intent/{proposal_id}/apply
  ↓
AI-1 Revision Service (actor=user, source=ai)
  ↓
Deterministic Campaign mutation + revision audit
```

The provider adapter never imports campaign models, receives a database
session, or commits data. Business services route by logical capability, never
by a vendor model name.

## Provider abstraction and routing

The implementation lives in `backend/app/services/ai/`:

- `provider.py`: narrow structured-output protocol and deterministic mock.
- `registry.py`: configured provider lookup.
- `router.py`: capability routes and a small deterministic complexity
  classifier.
- `orchestrator.py`: same-capability fallback and final schema validation.
- `openai_compatible.py`: the only provider-specific HTTP response handling.
- `revision_parser.py`: campaign context, proposal lifecycle, semantic
  validation, telemetry, and AI-1 handoff.

The shipped real adapter targets a configured OpenAI-compatible structured
chat-completion endpoint. Its base URL, API key, provider profile, and model
are runtime settings. The key is never persisted or logged.

## Proposal lifecycle

Statuses are `ready`, `clarification_required`, `unsupported`, `applied`,
`expired`, and `failed`. A ready proposal stores server-validated actions
and deterministic human-readable summaries. The browser applies only a
proposal ID; it cannot submit edited actions.

Default expiry is 15 minutes. Apply is rejected when the proposal expired,
belongs to another tenant/user, is not ready, the campaign is frozen, or
`draft_revision` changed. Proposals are never silently rebased.

`client_request_id` is unique per market/user. Replaying the same request
returns the original proposal; reusing the key with different semantics returns
409. Applying an already-applied proposal safely returns its linked AI-1
revision.

## Security and protected facts

Provider output is attacker-controlled input. It passes:

1. JSON decoding;
2. strict Pydantic discriminated-union validation (`extra=forbid`);
3. action-count and position limits;
4. campaign/market item-ID ownership validation;
5. protected-fact validation;
6. AI-1 state and optimistic-concurrency validation.

Price changes require explicit price wording and the exact numeric value in the
user instruction. Old-price changes additionally require explicit old-price
wording. Display-name changes require an explicit rename instruction and the
new name in the instruction. AI-2 never accepts `replace_image`, because the
minimal parser context does not include approved image-option IDs.

Context contains only campaign ID/title/revision/currency/language and current
item ID/order/name/price/visibility/emphasis. It excludes users, credentials,
webhook payloads, billing records, and unrelated tenant data.

## Resilience and cost controls

- `AI_ENABLED` and `AI_REVISION_ENABLED` are independent kill switches.
- Provider calls have a bounded 1–60 second timeout (15 seconds by default).
- Transient network/429/5xx failures receive at most one retry.
- Authentication, configuration, schema, ambiguity, and unsupported failures
  are not retried.
- Fallback must be explicitly configured and keep the same capability and
  structured-output contract.
- Instructions are capped at 2,000 characters.
- Proposals are capped at 20 actions by default.
- The shared fixed-window limiter allows five explicit requests per user per
  minute by default.
- No request occurs on keystrokes, page load, preview refresh, drag/drop, or
  manual AI-1 edits.

## Usage telemetry

`ai_usage_events` records tenant/user/campaign/proposal IDs, capability,
provider profile, configured model, request type, nullable token counts,
nullable estimated cost, latency, status, and safe error code. It deliberately
does not have prompt, instruction, API-key, phone, or email columns.

## Configuration

See `backend/.env.example` and `backend/.env.production.example` for the
`AI_*` settings. Keep both kill switches false until a provider/model/key are
configured and migration `20260826_0031` has been applied.

## Deliberate boundaries

- AI-3 image generation/editing, visual redesign, layout professionalization,
  multimodal critique, typography, palette generation, and final brochure
  polish are **not implemented**.
- AI-4 subscription quotas, token billing, invoice line items, and Stripe AI
  add-ons are **not implemented**.
- Telegram and WhatsApp free text are not connected to AI-2 in this phase. The
  reusable service can be integrated later without bypassing channel identity,
  tenant, lock, idempotency, or approval rules.
