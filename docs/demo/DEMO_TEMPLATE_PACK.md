# LeafletPilot Demo Template Pack

## Current template implementation

### Entities and scope

- `Template` persists name, slug, description, type, active state, global/market scope, and `config_json`.
- A global template has `is_global=true` and no `market_id`; a market template has `is_global=false` and a required `market_id`.
- Global and market slugs are independently unique.
- Templates are reusable because campaigns reference `template_id`; market onboarding can persist `default_template_id`.
- Backend list/get/create/update endpoints exist and enforce market roles. There is no template delete endpoint.

### Editing and preview

- The customer template list loads real templates and can toggle active state for authorized roles.
- The frontend has no create/edit configuration form even though backend POST/PATCH endpoints exist.
- Template detail loads real metadata/config, but its “Create preview” action is explicitly simulated.
- Real rendering occurs only through a campaign: campaign preview HTML and PDF/PNG export load the campaign's related template and pass it to the preview renderer.
- The seed provides two active global templates: `Premium Market` and `Compact Weekly`. Both are supermarket/weekly-promotion layouts.

### Demo-readiness conclusion

The model and campaign/export integration are a usable foundation, and runtime export succeeded. The current template library is not credible for a cross-sector demonstration because it lacks sector breadth, real direct preview, representative assets, and a frontend editor. The first credible pack should be curated and schema-driven; a full drag-and-drop editor can remain later scope.

## Minimum six-template pack

### 1. Fresh Week — Supermarket Weekly Promotion

- **Target sector:** Supermarket/grocery
- **Layout type:** A4 portrait, three-column product grid with one hero offer
- **Expected product count:** 12–18
- **Visual hierarchy:** Market masthead → date range → hero product/price → category bands → supporting products → terms
- **Required assets:** Market logo, food/product cutouts, category color tokens, price-burst shapes, optional freshness texture
- **Editable fields:** Title, dates, logo, colors, hero product, product order, prices/old prices, badges, footer/terms
- **Example CTA:** “Shop this week’s offers”
- **Demo value:** Closest to the current working seed and best low-risk proof of matching and multi-product export

### 2. Tech Launch — Electronics Campaign

- **Target sector:** Consumer electronics
- **Layout type:** A4 landscape or square social card set with comparison tiles
- **Expected product count:** 6–10
- **Visual hierarchy:** Campaign headline → flagship device → price/finance callout → feature chips → accessory grid → CTA
- **Required assets:** Transparent device images, dark gradient background, feature icons, warranty/finance badges
- **Editable fields:** Headline, hero device, specifications, installment text, discount, warranty, CTA, legal footer
- **Example CTA:** “Upgrade your setup”
- **Demo value:** Demonstrates non-grocery products, specifications, premium imagery, and fewer high-value items

### 3. New Season Edit — Fashion Seasonal Campaign

- **Target sector:** Fashion/apparel
- **Layout type:** Editorial portrait with lookbook hero and modular product cards
- **Expected product count:** 8–12
- **Visual hierarchy:** Seasonal story → lifestyle hero → curated looks → product/price cards → collection CTA
- **Required assets:** Licensed model/lifestyle image, transparent apparel cutouts, typography pair, neutral color palette
- **Editable fields:** Season title, hero image, collection name, product images, sizes, prices, promo badge, CTA
- **Example CTA:** “Discover the new collection”
- **Demo value:** Shows that templates can prioritize brand storytelling rather than dense price grids

### 4. Room Refresh — Home & Furniture Campaign

- **Target sector:** Furniture/homeware
- **Layout type:** A4 portrait room-scene hero with grouped product modules
- **Expected product count:** 8–14
- **Visual hierarchy:** Room inspiration → hero furniture set → room/category sections → dimensions/materials → delivery CTA
- **Required assets:** Styled room image, transparent furniture images, material swatches, delivery/assembly icons
- **Editable fields:** Theme, room image, product groups, dimensions, material/color, price, delivery terms, CTA
- **Example CTA:** “Refresh your home”
- **Demo value:** Demonstrates large imagery, grouped products, descriptive metadata, and service callouts

### 5. Glow Essentials — Beauty & Cosmetics Campaign

- **Target sector:** Beauty/cosmetics
- **Layout type:** Square social-first layout plus A4 adaptation, with one hero routine and product rail
- **Expected product count:** 6–9
- **Visual hierarchy:** Benefit headline → hero routine → product steps → price/offer → ingredient/benefit badges → CTA
- **Required assets:** Transparent product packshots, soft gradient/texture, benefit icons, skin-tone-safe palette
- **Editable fields:** Routine title, hero image, step labels, benefits, ingredients, price, gift badge, CTA
- **Example CTA:** “Build your glow routine”
- **Demo value:** Tests refined styling, small catalog sets, and reusable editorial hierarchy

### 6. Today’s Menu — Restaurant & Food Promotion

- **Target sector:** Restaurant/café/food service
- **Layout type:** A4 or digital menu with category sections and hero meal
- **Expected product count:** 10–16 menu items
- **Visual hierarchy:** Restaurant identity → hero meal/deal → menu categories → item/description/price → ordering CTA
- **Required assets:** Restaurant logo, licensed meal photography, dietary/allergen icons, optional QR placeholder
- **Editable fields:** Menu title, date/time, categories, item names/descriptions, prices, dietary flags, address, ordering CTA
- **Example CTA:** “Order now”
- **Demo value:** Proves templates can support text-heavy items and service businesses, not only packaged products

## Shared template contract for the first pack

Each template should use a validated configuration schema covering layout identifier, supported formats, product capacity, columns, color tokens, hero behavior, old-price visibility, badges, optional fields, and required asset slots. Renderer fallback behavior must be deterministic when an optional asset is absent. A template is demo-ready only when:

1. It appears in the real template list for the demo market.
2. Its direct preview uses the real renderer with synthetic products.
3. It can be selected in the campaign wizard.
4. Campaign preview and PDF/PNG export use the same configuration.
5. Required assets are local/licensed and pass an availability check.
6. Capacity overflow and missing-image behavior have tests.
7. At least one saved example campaign/export exists for the template.

## Suggested implementation sequence

1. Define and validate the shared `config_json` contract without building a free-form editor.
2. Connect template detail preview to the real renderer using an explicit synthetic preview dataset.
3. Add the supermarket template first and compare preview with export.
4. Add the other five templates and sector assets.
5. Seed example campaigns/exports for all six in the dedicated demo tenant.
6. Add a structured frontend editor for supported fields; defer drag-and-drop composition.
