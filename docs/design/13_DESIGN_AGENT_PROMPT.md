# Design Agent Prompt

Aşağıdaki prompt, Figma/UI tasarım agent’ına veya frontend geliştirme agent’ına verilebilir.

---

## Prompt

We are designing a B2B SaaS dashboard for LeafletPilot, an AI-assisted weekly supermarket leaflet and brochure automation platform.

LeafletPilot allows local grocery stores, Turkish/halal markets, butchers, delicatessens, greengrocers and small supermarket chains to send campaign product lists via Telegram/WhatsApp. The system parses product names and prices, matches products with a pre-approved product database, generates brochure previews using professional templates, then exports PDF and PNG files for print and social media.

The visual design should follow the same general line as our existing B2B products such as DisKlinikCRM and Comptario:

- Clean modern SaaS dashboard
- Professional and trustworthy
- White / slate / navy / blue color family
- Soft cards
- Clear tables
- Compact operational UI
- Subtle shadows
- Rounded corners
- Sidebar navigation
- Dashboard metrics
- Strong but not flashy visual hierarchy
- Minimal decorative elements
- Campaign colors only as accents, not as the main app identity

Do not design it like a colorful supermarket flyer. The app UI should be corporate and calm. The generated brochures can be colorful, but the dashboard itself should stay professional.

## Required Screens

Design the following screens:

1. Login
2. Dashboard
3. Campaigns List
4. Campaign Detail
5. New Campaign Wizard
6. Product Catalog
7. Add/Edit Product
8. Templates List
9. Template Detail / Preview
10. Bot Connections
11. Market Settings

## Navigation

Use a left sidebar with these sections:

- Dashboard
- Campaigns
- New Campaign
- Product Catalog
- Categories
- Brands
- Templates
- Markets
- Bot Connections
- Files
- Reports
- Settings

Group them visually into:

- Operations
- Catalog
- Design
- Management

## Color Direction

Suggested tokens:

```css
primary navy: #0F172A
primary blue: #2563EB
light blue: #EFF6FF
background: #F8FAFC
card: #FFFFFF
border: #E2E8F0
text main: #0F172A
text muted: #64748B
success: #059669
warning: #D97706
danger: #DC2626
```

## Dashboard Requirements

Dashboard should include:

- Monthly campaigns count
- Waiting approval count
- Missing product count
- Generated files count
- Recent campaigns table
- Bot connection status card
- Waiting approval list
- Missing products list
- Quick actions

Primary CTA:

```txt
New Campaign
```

## Campaign Detail Requirements

Campaign detail should be the most important operational screen.

Include:

- Campaign title
- Status badge
- Market name
- Template name
- Channel
- Created date
- Large brochure preview
- Product matching table
- Missing products panel
- Generated files panel
- Message history
- Activity history

Important actions:

- Regenerate Preview
- Generate Final Files
- Send to User
- Mark as Approved
- Request Revision

## Product Catalog Requirements

Product catalog should include:

- Search input
- Filters for brand, category, image status, active status
- Product table with thumbnail, name, brand, barcode, category, aliases, status
- Add Product button
- Excel Import button

## Add/Edit Product Requirements

Include fields:

- Product name
- Short product name
- Brand
- Category
- Barcode
- Package size
- Package type
- Alternative names
- Product image upload
- Image preview
- Active status

## Template Requirements

Template cards should show:

- Preview image
- Template name
- Use case
- Supported formats
- Max products per page
- Active/default status

Template types:

- Classic Grocery
- Premium
- Discount Focused
- Minimal
- Butcher/Deli
- Greengrocer

## Bot Connections Requirements

Support Telegram first, WhatsApp later.

Show:

- Provider
- Bot name / phone number
- Connection status
- Webhook status
- Last message time
- Test button
- Setup instructions

## UX Principles

- Keep the most important action visible.
- Use clear status badges.
- Make missing products highly visible.
- Never hide campaign generation errors.
- Use confirmation before final file generation.
- Show progress for parsing, matching, preview generation and file export.
- Use empty states with useful actions.
- Make the product feel simple even if the backend is complex.

## Output Style

Produce high-fidelity desktop dashboard screens first. Then create responsive mobile adaptations for the most important screens:

- Dashboard
- Campaign Detail
- Product Catalog
- New Campaign

Use realistic sample data from a Turkish/European grocery market.

Sample products:

- Coca-Cola 2L — 1.59€
- Eti Burçak — 0.99€
- Ülker Halley 10 pcs — 1.49€
- Torku Sucuk 400g — 5.99€
- Pınar Süt 1L — 0.89€
- Nutella 750g — 4.99€
- Sütaş Ayran 1L — 0.79€
- Bizim Yağ 5L — 8.99€

Sample market:

```txt
Anadolu Market
Albertville, France
```

Use Turkish UI labels for the first design version.
