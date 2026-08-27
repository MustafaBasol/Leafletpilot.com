# AI-3 post-approval professionalization

AI-3 is an explicit, versioned visual layer for an already approved campaign. It never writes to `campaigns.snapshot_json` or `campaign_items`.

A run stores the hash of the frozen snapshot, provider/model metadata, a strict enum-only plan and prompt-free usage telemetry. The model receives only item positions and visual availability, never product names, prices, quantities, legal text or images. The renderer validates and consumes the active plan only when its snapshot hash matches.

The allowed plan controls are existing renderer options: header/card/price/badge/image treatment, bounded prominence of up to three item positions, and two boolean-style emphasis settings. It cannot supply HTML, CSS, URLs, SVG, scripts, product ordering, or commercial facts.

Endpoints:

- `POST /campaigns/{campaign_id}/professionalization` creates a plan.
- `POST /campaigns/{campaign_id}/professionalization/{run_id}/apply` selects one stored plan.
- `POST /campaigns/{campaign_id}/professionalization/original` restores the original approved design.
- `GET /campaigns/{campaign_id}/professionalization` returns tenant-scoped plan history.

Configuration is runtime-only: set `AI_ENABLED=true`, `AI_PROFESSIONALIZATION_ENABLED=true`, `AI_PROFESSIONALIZATION_MODEL` (or reuse `AI_REVISION_MODEL`), provider/fallback settings, and the OpenAI-compatible runtime key. No secrets are persisted or sent to the browser.