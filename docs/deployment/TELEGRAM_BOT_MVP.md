# Internal Telegram Bot MVP

Phase 19B adds one central LeafletPilot Telegram bot for internal operators.
It is not public onboarding and it is not one bot per market.

## Architecture

- Telegram sends updates to `POST /api/integrations/telegram/webhook`.
- The route does not use LeafletPilot Bearer auth. It verifies
  `X-Telegram-Bot-Api-Secret-Token` against `TELEGRAM_WEBHOOK_SECRET`.
- Telegram users are authorized only through `telegram_accounts.telegram_user_id`.
  Telegram usernames are profile data, not identity.
- Market access still comes from active `MarketUser` memberships.
- The bot adapter calls existing campaign parsing, campaign creation, export,
  rendering, and storage-path services.
- Conversation state and Telegram update processing are stored in PostgreSQL.
- Local mounted storage remains the file backend.

## Environment

Telegram is disabled by default:

```text
TELEGRAM_BOT_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
TELEGRAM_BOT_USERNAME=
TELEGRAM_WEBHOOK_BASE_URL=
TELEGRAM_HTTP_TIMEOUT_SECONDS=20
TELEGRAM_HTTP_MAX_ATTEMPTS=1
```

When `TELEGRAM_BOT_ENABLED=true`, the backend requires:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`, at least 32 characters and not a placeholder
- `TELEGRAM_WEBHOOK_BASE_URL`
- HTTPS webhook base URL in production

Do not expose these values to the frontend and do not commit real values.

## Account Linking

Users must already exist in LeafletPilot. The script never creates users,
never grants market membership, and never bypasses `MarketUser`.

```powershell
cd backend
.\.venv\Scripts\python scripts\link_telegram_account.py `
  --email demo@leafletpilot.com `
  --telegram-user-id 123456789 `
  --username example_user
```

Re-running the same command is idempotent for the same user and Telegram ID.
A Telegram ID already linked to another user is rejected.

## Supported Commands

- `/start`: verify link and select a market automatically when there is only one.
- `/markets`: show active authorized markets.
- `/new`: start a campaign flow for `market_admin` and `market_staff`.
- `/status`: show selected market and current state.
- `/cancel`: clear the current bot flow and cancel a draft campaign when possible.
- `/help`: show command and plain-text list examples.

The MVP supports private chats only. Groups, supergroups, and channels are
rejected with a safe message.

## Campaign Flow

1. `/new`
2. Send a plain-text product list, one product per line.
3. The existing deterministic parser summarizes item count, warning count, and
   a bounded preview.
4. Send a campaign title.
5. The bot creates the campaign through the existing campaign service.
6. Confirm `Generate PDF + PNG`, send the list again, or cancel.
7. The bot creates files through the existing export service, resolves local
   paths through the storage service, and sends the PDF as a document and PNG
   as a photo.

No Excel, PDF, OCR, image input, voice transcription, item-by-item editing,
public signup, automatic retry queue, or background worker exists in this MVP.
Telegram outbound send/edit/file calls are not automatically retried because
they are non-idempotent POST operations.
Export generation is synchronous.

The database stores delivery markers for generated PDF and PNG sends, and
conversation-state rows are locked while the bot decides whether to create or
reuse campaigns and export jobs. These markers prevent normal webhook replay
duplicates. They do not make outbound Telegram delivery exactly once: if
Telegram accepts a file but the HTTP connection times out before the backend
receives the response, the database cannot know whether Telegram delivered it.
An explicit user retry after that ambiguous timeout may repeat a delivery.
Exactly-once outbound Telegram delivery would require a stronger durable
outbox and provider reconciliation design.

## Webhook Registration

Register the webhook manually after deployment. Use placeholders only in docs
and runbooks:

```bash
curl -X POST \
  "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" \
  -d "url=https://api.example.com/api/integrations/telegram/webhook" \
  -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"
```

Delete the webhook manually during rollback or disabling:

```bash
curl -X POST \
  "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/deleteWebhook"
```

The application does not call `getMe`, register webhooks, or contact Telegram
during startup.

## Local Test Procedure

1. Keep `TELEGRAM_BOT_ENABLED=false` for normal local API work.
2. Run backend tests with the fake Telegram client; tests must not contact
   `api.telegram.org`.
3. To test routing locally, enable Telegram with placeholder-like local values
   only in a private `.env`, then post a sample update with the secret header.
4. Do not use a real bot token unless you intentionally perform a manual smoke
   test against a private deployment.

## Production Checklist

- Apply Alembic revision `20260707_0006`.
- Set strong private Telegram environment values.
- Link only known internal users.
- Confirm each user has the correct active `MarketUser` membership.
- Register the webhook manually with the secret token.
- Confirm `/api/health` and `/api/health/db` remain unchanged.
- Confirm generated export files are still written under mounted local storage.

## Rollback

1. Delete the Telegram webhook manually.
2. Set `TELEGRAM_BOT_ENABLED=false`.
3. Redeploy the previous backend image if required.
4. Do not drop Telegram tables until all in-flight internal bot usage is
   confirmed inactive.

## Security Notes

- Do not log bot tokens, webhook secrets, raw authorization headers, full
  Telegram payloads, complete product lists, or file contents.
- Callback data is untrusted and is always revalidated against database
  membership and role state.
- Viewers cannot create campaigns or exports.
- `market_admin` and `market_staff` can complete the operational campaign flow.
