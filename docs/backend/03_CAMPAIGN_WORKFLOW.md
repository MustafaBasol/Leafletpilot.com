
# Campaign Workflow

## Status Lifecycle

```txt
draft
parsing
matching
missing_products
preview_ready
waiting_approval
revision_requested
approved
generating_files
completed
failed
cancelled
```

## State Details

### `draft`

Meaning: Campaign exists but product items are not finalized.

Entry triggers:

- Panel user creates a campaign.
- Telegram message starts a campaign but has not been parsed.

Saved data:

- Market, source channel, campaign name, template, requested formats.
- Raw text or incoming message reference if available.

Allowed transitions:

- `parsing`
- `cancelled`

### `parsing`

Meaning: The system is extracting product lines, names, prices, old prices, and optional barcodes.

Entry triggers:

- User submits raw list.
- Telegram text message is accepted.
- Later: Excel/PDF upload is accepted.

Saved data:

- `IncomingMessage`
- `CampaignItem.raw_text`
- Parsed fields such as `incoming_name`, `price_amount`, `old_price_amount`, `currency`
- Parsing errors if any.

Allowed transitions:

- `matching` when at least one item is parsed.
- `failed` when no usable product lines can be extracted.
- `cancelled`

### `matching`

Meaning: Parsed items are being matched against the catalog.

Entry triggers:

- Parsing completes.
- User reruns matching after adding products or aliases.

Saved data:

- `product_id` when matched.
- `match_status`, `match_method`, `match_score`.
- `MatchingSuggestion` rows for candidates.

Allowed transitions:

- `missing_products` when any item is `low_confidence`, `not_found`, or `new_product_needed`.
- `preview_ready` if all required items are matched or explicitly allowed without image.
- `failed` if matching job errors.

### `missing_products`

Meaning: One or more items require manual resolution.

Entry triggers:

- Matching score is below automatic threshold.
- No matching product is found.
- Matched product has no usable image and the template requires one.

Saved data:

- Matching suggestions.
- Missing product count.
- Activity log entry for operator/user review.

Allowed transitions:

- `matching` after manual product changes and rerun.
- `preview_ready` after all items are resolved, excluded, or marked `use_without_image`.
- `cancelled`

### `preview_ready`

Meaning: A preview file exists and can be reviewed.

Entry triggers:

- Preview export job succeeds.
- MVP placeholder preview record is created.

Saved data:

- `CampaignFile` with `file_type = preview_png`.
- Export job result.
- Template version used.

Allowed transitions:

- `waiting_approval` when preview is sent or displayed for approval.
- `revision_requested`
- `approved` if an operator marks it approved directly.
- `failed` if preview generation fails.

### `waiting_approval`

Meaning: Customer or market user must approve the preview before final files.

Entry triggers:

- Telegram bot sends preview and approval buttons.
- Panel user opens preview and approval action is required.

Saved data:

- Preview sent timestamp.
- Outgoing message metadata later.
- Activity log.

Allowed transitions:

- `approved`
- `revision_requested`
- `cancelled`

### `revision_requested`

Meaning: Customer requested changes after preview.

Entry triggers:

- Bot callback: price correction, product replacement, cancel, or free-text revision.
- Panel user clicks revision request.

Saved data:

- Revision note.
- `revision_count`.
- Updated campaign items if the correction is structured.
- Activity log entry.

Allowed transitions:

- `matching` when product data changed.
- `preview_ready` after regenerating preview.
- `cancelled`

### `approved`

Meaning: Preview was accepted and final files can be generated.

Entry triggers:

- User approves through panel.
- Telegram approval callback is received.
- Operator records customer approval during concierge MVP.

Saved data:

- `approved_at`
- `approved_by_user_id` or external approver metadata.
- Approval note.

Allowed transitions:

- `generating_files`
- `revision_requested` only if final generation has not started or operator explicitly reopens.
- `cancelled`

### `generating_files`

Meaning: Final PDF/PNG/social formats are being created.

Entry triggers:

- Approved campaign queues an export job.

Saved data:

- `ExportJob`
- `CampaignFile` rows in `pending` or `processing`.

Allowed transitions:

- `completed`
- `failed`

### `completed`

Meaning: Final requested files are ready and delivered or available for download.

Entry triggers:

- All required exports succeed.
- File delivery job succeeds or is manually marked sent.

Saved data:

- Ready file records.
- `sent_to_user_at` when delivered through bot.
- Completion activity.

Allowed transitions:

- Later: archive.
- Later: duplicate into new campaign.

### `failed`

Meaning: A blocking job failed.

Entry triggers:

- Parsing, matching, preview, export, storage, or delivery error.

Saved data:

- `last_error`
- Failed job attempt metadata.
- Activity log.

Allowed transitions:

- Previous actionable state when retry succeeds.
- `cancelled`

Retry rule:

- Store `attempt_count` and `max_attempts` on jobs.
- MVP can expose a manual "retry" action.
- Later workers should use exponential backoff and dead-letter reporting.

### `cancelled`

Meaning: The campaign was intentionally stopped.

Entry triggers:

- User cancels in bot or panel.
- Operator cancels duplicate or invalid request.

Saved data:

- Cancel reason.
- Actor metadata.
- Activity log.

Allowed transitions:

- None in MVP.
- Later: duplicate cancelled campaign into a new draft.

## Approval Rules

- Every campaign must be approved before final files are generated.
- Approval can come from panel, Telegram callback, or operator action.
- Approval records the actor, timestamp, preview file version, and note.
- If any campaign item changes after approval, approval must be cleared and preview regenerated.

## Revision Rules

- Revisions should preserve history, not overwrite the previous activity timeline.
- Structured revisions update campaign items directly.
- Free-text revisions create an operator task or activity entry in MVP.
- Each revision increments `revision_count`.

## Data Saved At Each Stage

| Stage | Must save |
|---|---|
| Intake | Incoming message, raw text, market, conversation |
| Parse | Campaign items with raw text and parsed fields |
| Match | Product reference, score, method, suggestions |
| Missing resolution | Manual decisions and alias/product changes |
| Preview | Preview file, template id/version, job result |
| Approval | Actor, timestamp, preview version |
| Final export | Export job, file records, storage keys |
| Delivery | Sent timestamp, provider metadata |

## MVP Guardrails

- Do not auto-complete campaigns without approval.
- Do not hide low-confidence matches.
- Do not discard raw incoming text.
- Do not generate final files while missing products remain unresolved unless each missing item is explicitly excluded or allowed without image.

## AI-1 Structured Draft Revisions

AI-1 adds a durable, deterministic revision ledger without connecting any AI
provider. All panel, messaging, system, and future AI-originated changes use a
validated `RevisionCommand` and the same revision service.

```text
UI or future AI intent parser
        -> structured RevisionCommand
        -> deterministic revision service
        -> CampaignItem and builder metadata
        -> deterministic preview / export
```

AI parses intent in a later phase; it must not directly mutate campaign rows,
product catalog data, CSS, or brochure geometry. The current allowed action
set is `move_item`, `remove_item`, `restore_item`, `update_price`,
`update_display_name`, `set_hero`, `set_item_emphasis`, and `replace_image`.
Price input is Decimal validated. Image replacement accepts only an existing,
safe catalog image belonging to the current item's catalog product.

Each successful command requires a client request ID and expected draft
revision. `campaign_revisions` stores the requested actions, before/after
campaign-only state, source, actor, tenant, and monotonic sequence. The
`(campaign_id, request_id)` and `(campaign_id, sequence)` uniqueness
constraints make delivery retries idempotent and prevent silent version
collisions. An undo is a new revision event that restores the immediately
preceding revision's before-state; it never deletes history.

A revision changes campaign-only presentation fields only: product ordering,
hidden state, display name, price, emphasis/hero state, and a selected catalog
image reference. It never overwrites canonical `Product` or `MarketProduct`
data. Hidden products are excluded from the deterministic render payload.

### Approval freeze

Approval validates that the campaign is active, has at least one visible item,
that every visible item has a display name and Decimal price, and that template
slot capacity is respected. It records `approved_revision` and saves the exact
render payload in `snapshot_json`, augmented with approval timestamp and
market/campaign identity. That payload includes the resolved ordering, display
text, prices, template/version, builder configuration, image keys, semantic
emphasis, currency, and language.

Once `frozen_at` / `finalized_at` is set, draft mutation and revision endpoints
return a conflict. Preview and export render from the immutable snapshot, so a
later catalog change cannot change an approved brochure.

### AI-1 hardening contract

- Approval and legacy finalization require the displayed expected draft revision;
  the locked campaign returns 409 and its current revision when stale.
- Public panel revision and undo payloads forbid source. The server creates a
  trusted panel source while internal trusted callers retain their source.
- A duplicate request ID succeeds only when source, expected revision, and
  normalized actions have the same canonical fingerprint; otherwise it is 409.
- Retained render-affecting legacy workflows lock the campaign and advance the
  shared draft version and durable server-authored ledger event.
- Final export requires an already-frozen campaign and never auto-finalizes.
- Approval-time catalog refresh validates references only. It writes no
  CampaignItem presentation field, preserving campaign display, prices,
  visibility, hero/emphasis, image override, and ordering in the snapshot.
- Undo restores one normal structured mutation. A latest undo or server
  workflow event returns 409 instead of acting as undocumented redo.
