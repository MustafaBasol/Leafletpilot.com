# Telegram MVP Plan

## Scope

Telegram MVP should prove the full customer loop:

1. Customer sends a product list.
2. Backend creates a campaign.
3. Backend parses and matches products.
4. Customer receives status and preview.
5. Customer approves or requests revision.
6. Backend records final file delivery.

No real Telegram code is added in Phase 4.

## Bot Setup

MVP setup steps for Phase 10:

1. Create bot through BotFather.
2. Store bot token as an encrypted secret or environment variable.
3. Create `BotConnection` for the market with `provider = telegram`.
4. Configure webhook URL: `/api/v1/webhooks/telegram/{connectionId}`.
5. Use a webhook secret path or header validation.
6. Send test message and update `webhook_status`.

## Webhook Flow

Route:

```txt
POST /api/v1/webhooks/telegram/{connectionId}
```

Flow:

1. Validate connection and secret.
2. Store raw payload in `IncomingMessage.payload`.
3. Resolve `Conversation` by `external_chat_id`.
4. Identify market from `BotConnection`.
5. Acknowledge Telegram quickly.
6. Process message synchronously for MVP or queue a job later.

## Incoming Text Message Flow

1. User sends text product list.
2. Backend stores `IncomingMessage`.
3. Conversation state changes to `parsing_list`.
4. Backend creates `Campaign` with `source_channel = telegram`.
5. Backend creates `CampaignItem` rows.
6. Matching runs.
7. Bot replies with counts:

```txt
Analiz tamamlandi.
Toplam urun: 24
Eslesen urun: 22
Kontrol gereken urun: 2
```

8. If missing products exist, send review options or mark for operator.
9. If all items are acceptable, offer preview generation.

## Incoming Excel/PDF Placeholder Flow

MVP placeholder, not full implementation:

1. User sends file.
2. Backend stores file metadata and original upload key.
3. Backend creates `IncomingMessage` with `message_type = file`.
4. Bot replies:

```txt
Dosyanizi aldim. Excel/PDF okuma bu MVP'de operator kontroluyle ilerleyecek.
```

5. Operator can later create campaign items manually or through a later parser.

Do not implement Excel/PDF parsing until the core text flow is stable.

## Campaign Creation From Message

Campaign defaults:

- `market_id`: from bot connection.
- `name`: generated from date, for example `Telegram Kampanyasi - 2026-07-02`.
- `template_id`: market default template.
- `requested_formats`: market default output formats.
- `status`: `parsing`, then `matching`.
- `conversation_id`: active Telegram conversation.
- `incoming_message_id`: source message.

## Preview Approval Flow

When preview is ready:

1. Store `CampaignFile` with `file_type = preview_png`.
2. Send preview image to Telegram chat.
3. Send inline buttons:

```txt
Onayla
Fiyat Duzelt
Urun Degistir
Iptal Et
```

4. Store callback payloads with campaign id and action.
5. On approval, set campaign to `approved`.
6. Queue final export job.

## File Delivery Flow

After final exports:

1. Find ready `CampaignFile` records.
2. Send PDF and image files to chat.
3. Set `sent_to_user_at`.
4. Add activity log entry.
5. Set campaign `completed` if all required files are ready and delivered.

MVP can use placeholder file records until real export exists.

## Conversation State Management

Use `Conversation.state` values:

```txt
idle
waiting_for_product_list
parsing_list
matching_products
waiting_for_missing_product_action
preview_generating
waiting_for_approval
waiting_for_price_correction
waiting_for_product_replacement
generating_final_files
completed
cancelled
failed
```

Rules:

- One active campaign per conversation in MVP.
- `/new` starts a fresh campaign if no active campaign is waiting.
- `/status` returns active campaign state.
- `/cancel` cancels active campaign after confirmation.

## Rate Limit Awareness

MVP rules:

- Reply quickly to webhook requests.
- Do not send many separate messages for every product.
- Batch review summaries.
- Store failed outgoing messages for retry.
- Avoid resending files repeatedly on refresh/polling.

Later:

- Add outgoing message queue.
- Add provider-specific rate limit handling.
- Add idempotency keys for callbacks.

## What Not To Implement In MVP

- WhatsApp.
- Multi-campaign conversation switching.
- Full Excel/PDF parsing.
- AI parsing.
- Rich operator handoff.
- Payment/subscription gates.
- Automatic social media publishing.
