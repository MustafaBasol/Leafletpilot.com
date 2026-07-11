# Pilot flyer builder

## Market-user flow

1. Select the market, create categories, then add active products with brand, unit, promo price, currency, order, and a primary product image.
2. Open **New Campaign**, choose a flyer template, set the title and validity date, and select/order products.
3. Use the campaign preview to confirm the actual product cards, images, prices, badges, and market-owned assets.
4. Export PNG and/or PDF. Files are stored below the owning market and campaign and appear in campaign history.

## Preset pack

The MVP uses one shared retail-promo language with 4, 6, 9, 12, and 16 product slots. Each preset defines its grid columns/rows, while the renderer supplies the common hero, validity, rounded cards, price badge, and warm background treatment. A campaign cannot exceed its selected preset's slot count.

## Required assets

Use a market-owned logo and primary product images. Product image records must reference safe storage keys under the owning market; external demo URLs are not used by the renderer. Replace or remove an image by changing the primary image record while keeping the product and market scope intact.

## Export behavior

Preview HTML is deterministic and does not create export history. Final PNG/PDF exports create market-owned campaign files through the existing export job pipeline. Rendering embeds local product images, validates output signatures, and rejects unsafe storage paths.

## Pilot checklist

- Select the intended market and verify its role.
- Create at least one category and four active products.
- Add a primary image to each product and confirm the image status.
- Create a campaign with a matching preset slot count.
- Check title, validity, stock notice, brand/unit text, prices, and product order in preview.
- Export both PNG and PDF, then download from campaign history.
- Confirm another market cannot see the campaign, assets, or export files.
