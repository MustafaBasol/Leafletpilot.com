# Template Gallery

The templates page is preview-first: **Önerilen**, **Hazır Şablonlar**, and **Şablonlarım**. Global implementation terminology is not shown to market users. Adopted global copies are intentionally excluded from *Şablonlarım* so one logical stock design is not duplicated.

`GET /api/templates/{id}/preview-thumbnail` uses the existing deterministic brochure renderer with a fixed 16-item supermarket demo basket. It writes a PNG beneath storage using a content hash of the template id, version, name, and config; later requests reuse that file. Updating a template increments its version, so its cache key changes without storing binary image data in the database.

Suitability is derived from existing `slot_count`/slug fields, with safe legacy fallbacks; no migration is needed. The deterministic recommendation chooses an active template that contains the product count, then the nearest range midpoint. It makes no AI call and never changes a chosen campaign template. New Campaign shows the same cached visual cards and only highlights the recommendation.

Preview access first resolves normal template scope. A market-specific template therefore cannot be rendered by another tenant. Generic thumbnail data deliberately never reads tenant products. Large previews currently use the generic canonical market, avoiding cache invalidation tied to mutable market branding.