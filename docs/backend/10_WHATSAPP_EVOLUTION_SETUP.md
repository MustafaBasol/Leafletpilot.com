# Central WhatsApp Channel — Evolution API Setup

Operator runbook for the platform-owned WhatsApp channel: **ONE** LeafletPilot
WhatsApp number, driven by **ONE** Evolution API v2 instance, shared by
**every** market. There is no per-market WhatsApp number and no per-market
Evolution instance.

Code entry points, for reference while reading this doc:

- `backend/app/core/config.py` — `evolution_*` / `whatsapp_*` settings and
  their validation (`_validate_enabled_evolution_settings`).
- `backend/app/api/routes/whatsapp_webhook.py` — the inbound webhook route.
- `backend/app/integrations/whatsapp/client.py` — the outbound Evolution
  client (send/connection-state calls LeafletPilot makes at runtime).
- `backend/app/integrations/whatsapp/service.py` — verification and message
  routing logic.
- `backend/app/api/routes/platform_whatsapp.py` — what Platform Admin can see
  and do.
- `backend/app/api/routes/whatsapp.py` — the market-facing verification
  endpoints behind the Ekip ("Team") page.

## 1. Overview and architecture decision

**Evolution API is not part of `docker-compose.production.yml`.** LeafletPilot
treats it as an external/self-hosted dependency it connects to over HTTP(S),
not a service it owns the lifecycle of. This is deliberate:

- Evolution needs its own Postgres and Redis and a persistent WhatsApp
  session. Folding that into the LeafletPilot stack would couple two very
  different lifecycles — a routine backend deploy/rollback should never risk
  dropping the one live WhatsApp session the whole platform depends on.
- Connecting the number requires an interactive QR/pairing-code scan. That
  has no place in an automated `docker compose up` on deploy.
- If an Evolution instance already exists in the operator's infrastructure,
  LeafletPilot should be pointed at it (`EVOLUTION_API_BASE_URL`) rather than
  a second instance being silently started alongside it.

What LeafletPilot's own compose file *does* carry is the environment wiring —
the `EVOLUTION_*` / `WHATSAPP_*` / `LEAFLETPILOT_WHATSAPP_NUMBER` variables on
the `backend` and `migration` services in `docker-compose.production.yml`.
The `backend` service is already attached to the `egress` network (the one
network in that file that is not `internal: true`), which is what lets it
reach an external Evolution host over HTTPS.

`deploy/evolution/docker-compose.evolution.example.yml` is a **reference**
stack (Evolution + its own Postgres + its own Redis) for an operator who does
not already run Evolution. It is explicitly labelled as an example to deploy
separately, and must not be merged into `docker-compose.production.yml`.

### Flow

```
 Market user's phone           Central WhatsApp number        LeafletPilot backend
 (their own WhatsApp)          (LEAFLETPILOT_WHATSAPP_NUMBER)  + Evolution API instance
        |                               |                               |
        | 1. "Ekip" page -> member row  |                               |
        |    -> "WhatsApp ile Dogrula"  |                               |
        |    LeafletPilot generates a   |                               |
        |    one-time code (LP-XXXX-XXXX)                               |
        |<------------------------------|<------------------------------|
        |                               |                               |
        | 2. User sends the code AS A   |                               |
        |    WhatsApp MESSAGE to the    |                               |
        |    central number ----------->|                               |
        |                               |-- Evolution instance receives-|
        |                               |   the message, fires webhook  |
        |                               |------------------------------>| POST /api/webhooks/evolution/whatsapp
        |                               |                               | header: X-Evolution-Webhook-Token
        |                               |                               |
        |                               |                               |-- verify header secret (constant-time)
        |                               |                               |-- normalize event (MESSAGES_UPSERT)
        |                               |                               |-- resolve REAL sender phone from
        |                               |                               |   Evolution's own key.senderPn /
        |                               |                               |   remoteJidAlt (never the claimed
        |                               |                               |   phone typed into the LeafletPilot UI)
        |                               |                               |-- match one-time code hash
        |                               |                               |-- mark UserWhatsAppIdentity verified
        |                               |                               |   for that user + market
        |                               |<-- confirmation reply --------|
        |<------------------------------|                               |
        |                               |                               |
        | 3. Later: user sends a        |                               |
        |    product list as a normal   |                               |
        |    WhatsApp message --------->|------ MESSAGES_UPSERT ------->|-- resolve verified identity
        |                               |                               |-- re-check MarketUser membership
        |                               |                               |   (live, not cached)
        |                               |                               |-- command router
        |                               |                               |   (app/integrations/whatsapp/commands.py)
        |                               |                               |-- campaign / brochure generation
        |                               |<-- reply / status updates ----|   service
        |<------------------------------|                               |
```

The identity that matters is **who actually sent the WhatsApp message**
(Evolution's `senderPn`/`remoteJidAlt`), not the phone number a user typed
into the LeafletPilot UI when requesting a code — the claimed number is only
ever advisory (see `service.py` module docstring).

## 2. Prerequisites

- A running **Evolution API v2.x** instance (self-hosted, or the reference
  stack in `deploy/evolution/`). The Evolution client
  (`app/integrations/whatsapp/client.py`) targets v2 endpoint shapes; do not
  point it at a v1 instance.
- A **dedicated** WhatsApp number for the central LeafletPilot channel. It
  **must not** be a number already registered to a personal WhatsApp account
  in active use — connecting it to Evolution takes over that WhatsApp
  session (linked-device pairing), which will disrupt or disconnect the
  existing personal usage of that number.
- HTTPS reachability of `https://api.leafletpilot.com/api/webhooks/evolution/whatsapp`
  from the Evolution instance (adjust the host if not deploying against the
  production domain). Evolution must be able to reach this URL directly —
  there is no LeafletPilot-initiated polling fallback.

## 3. Evolution instance creation

> **Uncertainty notice.** LeafletPilot's own Evolution client
> (`backend/app/integrations/whatsapp/client.py`) only implements the
> *ongoing runtime* calls it needs (`POST /message/sendText/{instance}`,
> `POST /message/sendMedia/{instance}`, `GET
> /instance/connectionState/{instance}`) — those three are verified against
> this codebase. Instance **creation**, QR/pairing-code retrieval, and
> webhook **configuration** are one-time setup steps performed directly
> against Evolution's own API and are not exercised by any LeafletPilot code
> path, so the exact request/response shapes below are given as the
> documented Evolution API v2 convention, not as something this repo
> verifies. Evolution's setup endpoints have changed shape between minor
> versions — before running these against a real instance, confirm the exact
> routes and JSON shape against that instance's own Swagger/OpenAPI docs
> (commonly served at `{EVOLUTION_API_BASE_URL}/docs` or via its Manager UI).

Create the instance:

```bash
curl -X POST "https://evolution.example.com/instance/create" \
  -H "apikey: <EVOLUTION_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "instanceName": "leafletpilot-central",
    "integration": "WHATSAPP-BAILEYS",
    "qrcode": true
  }'
```

`instanceName` here must match `EVOLUTION_INSTANCE_NAME` exactly — LeafletPilot
sends it as a path segment on every request
(`app/integrations/whatsapp/client.py::_instance_path`).

Fetch the QR code / pairing code (if it was not returned inline by the create
call above, or to refresh an expired one):

```bash
curl -X GET "https://evolution.example.com/instance/connect/leafletpilot-central" \
  -H "apikey: <EVOLUTION_API_KEY>"
```

## 4. Connecting the WhatsApp number

1. On the **dedicated** device/number chosen in step 2 (Prerequisites), open
   WhatsApp → Linked Devices → Link a Device, and either scan the QR code
   returned above or enter the pairing code, depending on which the instance
   returned.
2. Confirm the session came up:

```bash
curl -X GET "https://evolution.example.com/instance/connectionState/leafletpilot-central" \
  -H "apikey: <EVOLUTION_API_KEY>"
```

   This route is verified against this codebase
   (`EvolutionClient.fetch_connection_state`); expect a response shaped like:

   ```json
   {"instance": {"instanceName": "leafletpilot-central", "state": "open"}}
   ```

   `state` must be `"open"` before continuing. `"connecting"` means the QR/
   pairing step has not completed yet; `"close"` means the session dropped or
   was never established.

## 5. Webhook configuration

> Same uncertainty notice as section 3 applies to the exact webhook-set
> request shape — confirm against the running instance's own API docs.

Set the webhook on the instance:

```bash
curl -X POST "https://evolution.example.com/webhook/set/leafletpilot-central" \
  -H "apikey: <EVOLUTION_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "webhook": {
      "url": "https://api.leafletpilot.com/api/webhooks/evolution/whatsapp",
      "enabled": true,
      "headers": {
        "X-Evolution-Webhook-Token": "<EVOLUTION_WEBHOOK_SECRET>"
      },
      "events": ["MESSAGES_UPSERT"]
    }
  }'
```

- **URL**: `https://api.leafletpilot.com/api/webhooks/evolution/whatsapp`
  exactly (`backend/app/api/routes/whatsapp_webhook.py`, router prefix
  `/webhooks/evolution` + route `/whatsapp`).
- **Header**: `X-Evolution-Webhook-Token: <EVOLUTION_WEBHOOK_SECRET>` — must
  be the same value as `EVOLUTION_WEBHOOK_SECRET` configured on the
  LeafletPilot backend. The webhook handler also accepts an
  `Authorization: Bearer <secret>` header as a fallback (some reverse-proxy
  topologies rewrite custom headers), but the dedicated header is the primary
  mechanism and the one Evolution's `webhook.headers` config is meant for.
- **Events**: LeafletPilot only acts on `MESSAGES_UPSERT`
  (`app/integrations/whatsapp/schemas.py::INBOUND_MESSAGE_EVENTS`). Subscribing
  to additional events (`CONNECTION_UPDATE`, `PRESENCE_UPDATE`, ...) is
  harmless — the webhook route normalizes and acknowledges any well-formed
  JSON body, and an event type outside `INBOUND_MESSAGE_EVENTS` is recorded
  (for the Platform Admin "last webhook" indicator) and then ignored
  (`process_webhook_event` returns `"ignored_event_type"`), never a 4xx/5xx.
  There is no need to narrow the subscription list precisely.

## 6. LeafletPilot configuration

Set on the backend (and `migration`, for consistency — it reads the same
`Settings` object even though it never calls Evolution) — see
`backend/.env.production.example` and the `backend`/`migration` `environment:`
blocks in `docker-compose.production.yml`:

| Variable | Purpose |
|---|---|
| `EVOLUTION_WHATSAPP_ENABLED` | Master switch. `false` disables the webhook route (404) and all channel logic. |
| `EVOLUTION_API_BASE_URL` | Base URL of the Evolution instance, e.g. `https://evolution.example.com`. |
| `EVOLUTION_API_KEY` | Evolution's `apikey` header value — same as `AUTHENTICATION_API_KEY` on the Evolution side. |
| `EVOLUTION_INSTANCE_NAME` | Must match the `instanceName` created in section 3. |
| `EVOLUTION_WEBHOOK_SECRET` | Shared secret for `X-Evolution-Webhook-Token` — same value configured in section 5. |
| `LEAFLETPILOT_WHATSAPP_NUMBER` | The dedicated number, E.164 (`+33612345678`). |
| `EVOLUTION_HTTP_TIMEOUT_SECONDS` | Timeout for outbound calls to Evolution (default `20`). |
| `WHATSAPP_VERIFICATION_EXPIRE_MINUTES` | How long a one-time code stays valid (default `10`). |
| `WHATSAPP_VERIFICATION_RESEND_COOLDOWN_SECONDS` | Minimum gap between code requests (default `60`). |
| `WHATSAPP_VERIFICATION_MAX_ATTEMPTS` | Attempts allowed against one code before it fails (default `5`). |
| `WHATSAPP_RATE_LIMIT_WINDOW_MINUTES` | Window used by the rate limits below (default `10`). |
| `WHATSAPP_VERIFICATION_REQUEST_LIMIT` | Max verification requests per window (default `5`). |
| `WHATSAPP_INBOUND_MESSAGE_LIMIT` | Max inbound messages per sender per window (default `60`). |
| `WHATSAPP_WEBHOOK_IP_LIMIT` | Max webhook deliveries per source IP per window (default `600`). |

After setting these, restart the `backend` container (and re-run the
`migration` service if this is the first deploy since the WhatsApp tables
were added — `alembic upgrade head`). Config validation runs at process
startup (`Settings.validate_security_settings`); a misconfigured value (short
webhook secret, malformed number, non-HTTPS base URL in production) fails
startup immediately rather than at first use.

## 7. Verification smoke test

1. **Platform Admin → WhatsApp** → click **"Bağlantıyı Test Et"**
   (`POST /platform/integrations/whatsapp/connection-test`). Expect `ok:
   true` and `state: "open"`. If not, stop here — fix the Evolution
   connection before testing verification (see Troubleshooting).
2. On a market: **Ekip** page → pick a team member → **"WhatsApp ile
   Doğrula"**. LeafletPilot shows a one-time code and (optionally) a
   `wa.me` deep link to the central number.
3. From that member's own phone, send the code as a WhatsApp message to the
   central LeafletPilot number (typing it, or following the deep link).
4. Within a few seconds the Ekip row should flip to **"Doğrulandı"**
   (`whatsappStatus.js::WHATSAPP_STATUS_LABELS.verified`).
5. Back in **Platform Admin → WhatsApp**:
   - The health card's "last webhook" timestamp should have just moved.
   - The identity should appear in the identities list
     (`GET /platform/integrations/whatsapp/identities`) with `status:
     verified`, the masked phone, and the correct market(s) under
     `markets`.

If step 4 does not happen, check the backend logs for the webhook's outcome
tag (`process_webhook_event` returns one of `verified`,
`verification_unknown_code`, `verification_expired`,
`verification_attempt_limit`, `verification_failed_*`, `ignored_unknown_sender`,
etc.) before assuming the webhook never arrived — many failure paths still
reach the handler and reply to the user, they just don't verify anything.

## 8. Security controls

- **Shared-secret header, not a signature.** Evolution API does not sign its
  webhook bodies (no HMAC digest to verify). The strongest control
  compatible with the deployed version is therefore the configured
  `X-Evolution-Webhook-Token` value, compared with `hmac.compare_digest` in
  constant time against both the dedicated header and an `Authorization:
  Bearer` fallback (`whatsapp_webhook.py::_valid_webhook_token`) — every
  candidate present is compared, so the number of comparisons never leaks
  which header carried the (in)correct value.
- **Rate limiting**, all backed by the same fixed-window bucketed counter
  (`app/services/rate_limit.py`, reusing the `signup_throttles` table that
  already serves public signup — keys are HMAC-hashed before storage, so a
  phone number or user id never lands in that table in the clear):
  - Per source IP on the webhook route itself (`WHATSAPP_WEBHOOK_IP_LIMIT`),
    checked before the payload is even parsed for business logic.
  - Per sender phone on inbound message processing
    (`WHATSAPP_INBOUND_MESSAGE_LIMIT`), so a single hostile/misbehaving
    number cannot flood the command router.
  - Per **target user** on verification code requests
    (`WHATSAPP_VERIFICATION_REQUEST_LIMIT` within
    `WHATSAPP_RATE_LIMIT_WINDOW_MINUTES`), keyed on the user being verified
    rather than on the admin making the request — so an admin cannot burn
    through one member's limit and it is the member's identity that is
    protected. A separate per-user resend cooldown
    (`WHATSAPP_VERIFICATION_RESEND_COOLDOWN_SECONDS`) sits in front of it.
  - A separate, tighter limit on the "unverified sender" auto-reply itself
    (3 per window, hardcoded) so an unknown number can't turn the channel
    into a reflector.
- **Idempotency on redelivery.** Evolution (and WhatsApp) redeliver.
  `_begin_event` claims each inbound event by a
  `(instance, event_type, message_id)` key before any side effect runs, with
  a 5-minute processing lease so a crash mid-flight becomes retryable instead
  of permanently stuck. A verification code can never be consumed twice by a
  redelivered webhook, and a campaign can never be created twice from one
  message.
- **Hashed, single-use verification codes.** Codes are stored and matched by
  hash only (`hash_whatsapp_verification_code`); the plaintext code is never
  persisted. A code is consumed (`status` moves out of `pending`) on its
  first resolution, success or failure, and audit rows carry the masked
  phone and a reason code — never the plaintext code, its hash, or the
  unmasked number.
- **Defence in depth, not the only check.** As additional hardening, restrict
  the webhook path at the reverse proxy to Evolution's known source IP(s).
  This must never be the *sole* control — reverse-proxy topologies and
  hosting providers change source IPs, and the header secret is what the
  application-layer check actually relies on. Treat an IP allow-list as a
  belt to the header secret's braces, not a replacement for it.

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Webhook call returns `401` | `EVOLUTION_WEBHOOK_SECRET` mismatch between LeafletPilot and the value configured in Evolution's webhook headers | Re-check both sides byte-for-byte; regenerate and re-set on both if unsure. Remember the check is exact-match, not prefix/substring. |
| Webhook is never received at all | Wrong webhook URL, wrong/empty event subscription, or Evolution cannot reach the LeafletPilot host over HTTPS | Re-run the `webhook/set` call from section 5; confirm from the Evolution host that `https://api.leafletpilot.com/api/webhooks/evolution/whatsapp` is reachable (DNS, firewall, TLS); confirm `MESSAGES_UPSERT` (or a superset including it) is subscribed. |
| `connectionState` is not `"open"` | The linked-device session dropped (phone offline too long, manually unlinked, WhatsApp security event) | Re-run the QR/pairing flow in section 4. LeafletPilot's connection-test in Platform Admin will keep reporting the stale state until re-paired. |
| Verification never completes even though the code was sent | User messaged the wrong number (not the central `LEAFLETPILOT_WHATSAPP_NUMBER`), or the code expired (`WHATSAPP_VERIFICATION_EXPIRE_MINUTES`), or the attempt limit was hit | Confirm the number shown in the Ekip UI matches `LEAFLETPILOT_WHATSAPP_NUMBER` exactly; have the user request a fresh code (subject to the resend cooldown) and resend promptly. |
| Backend logs a warning: inbound message "sender could not be resolved" / `ignored_unknown_sender` | The connected Evolution version is not sending `senderPn` (or a resolvable `remoteJidAlt`) for `@lid`-addressed chats — a known gap in some Evolution/Baileys versions for certain WhatsApp accounts | Upgrade the Evolution instance to a version that reliably populates `senderPn` for `@lid` deliveries; there is no safe fallback LeafletPilot can use instead (the envelope's top-level `sender` field is the *instance's own* number, so it is deliberately never used as a stand-in — see `schemas.py::_resolve_sender`). |
| Platform Admin connection test fails with an auth error | `EVOLUTION_API_KEY` wrong, or Evolution's `AUTHENTICATION_API_KEY` was rotated without updating LeafletPilot | Re-sync the two values; restart the backend after changing `EVOLUTION_API_KEY`. |
| Startup fails with a `Settings` validation error mentioning `EVOLUTION_*`/`WHATSAPP_*` | One of the enabled-channel constraints in `_validate_enabled_evolution_settings` was not met (short/placeholder webhook secret, non-E.164 number, non-HTTPS base URL in production, missing API key/instance name) | Read the raised message — it names the exact field and rule; fix the corresponding variable in `backend/.env.production.example`-derived config or the compose `environment:` block. |

## 10. Rollback

Disabling the channel requires no code changes:

1. Set `EVOLUTION_WHATSAPP_ENABLED=false` (compose `environment:` block or
   the deployed `.env`).
2. Restart the `backend` container.

Effects:

- The webhook route (`POST /api/webhooks/evolution/whatsapp`) starts
  returning `404` again, identical to how a disabled Telegram integration's
  webhook behaves — it does not advertise that the route exists.
- No new verification codes can be requested and no inbound WhatsApp
  messages are processed.
- Already-verified `UserWhatsAppIdentity` rows, verification history, and
  webhook event ledger rows are **not deleted** — re-enabling later resumes
  from the same state rather than requiring every user to re-verify.
- The Evolution instance itself is unaffected by this flag; it keeps running
  and keeps its WhatsApp session connected (it just has nowhere to deliver
  webhooks to, or Evolution will get 404s back if it tries — which is fine,
  it does not retry-storm the endpoint).
- **Telegram is unaffected either way.** `TELEGRAM_BOT_ENABLED` is an
  entirely separate flag; toggling `EVOLUTION_WHATSAPP_ENABLED` never touches
  the Telegram bot, its webhook, or its conversations.

To fully decommission (rare — only once no rollback is anticipated), also
disconnect and delete the Evolution instance, and stop
`deploy/evolution/docker-compose.evolution.example.yml` if that reference
stack was used.
