# Automatic final AI brochure and market logo

Approval freezes the commercial snapshot and immediately queues one AI brochure-image professionalization run for that snapshot. The deterministic approved render is retained as the original fallback.

The worker renders the frozen source image, sends only that image, the optional market logo, and immutable brochure facts to the configured image-edit capability. It never accepts AI HTML, CSS, or executable output. A candidate image is OCR/fact checked before it is stored as a versioned campaign PNG and made active. Provider, timeout, OCR, or validation failures leave the original approved export usable.

Set `AI_ENABLED=true`, `AI_PROFESSIONALIZATION_ENABLED=true`, `AI_PROFESSIONALIZATION_PROVIDER`, and `AI_PROFESSIONALIZATION_MODEL` only for a provider whose OpenAI-compatible `/images/edits` endpoint is available. The existing rate limit and maximum-runs settings remain the cost controls. Disable the feature switch to keep deterministic approval/export only.

Market administrators use `PUT /api/market/logo`, `GET /api/market/logo`, `GET /api/market/logo/content`, and `DELETE /api/market/logo`. Uploads use the existing bounded image pipeline and tenant-scoped storage. A logo is incorporated into deterministic snapshots and supplied to AI. Until a graphic-logo validator is configured, a candidate where logo identity cannot be verified is rejected rather than guessed.

Exports select the accepted professional PNG when it is active; otherwise they use the approved deterministic renderer. The original selection always remains recoverable.