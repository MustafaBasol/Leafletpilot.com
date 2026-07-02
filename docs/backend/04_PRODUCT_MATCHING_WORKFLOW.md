# Product Matching Workflow

## Goal

Match noisy incoming product lines to approved catalog products while preserving human control for low-confidence cases.

Input example:

```txt
Bizim Aycicek Yagi 5 Lt - 8.99
```

Output:

- Parsed product name: `Bizim Aycicek Yagi 5 Lt`
- Product match: `Bizim Yag 5L`
- Price: `8.99`
- Match method: `alias`
- Score: `94.00`
- Status: `matched`

## Normalization

Before matching, normalize both incoming names and catalog fields:

- Lowercase.
- Trim whitespace.
- Remove repeated spaces.
- Normalize Turkish characters where useful for search fallback.
- Remove punctuation that does not affect meaning.
- Normalize units: `lt`, `litre`, `l` -> `l`; `gr`, `g` -> `g`.
- Keep original raw text unchanged.

## Match Order

### 1. Exact Match

Compare normalized incoming name with `Product.normalized_name` and `Product.short_name`.

Result:

- Score: 100
- Status: `matched`
- Method: `exact`

### 2. Alias Match

Compare normalized incoming name with `ProductAlias.normalized_alias`.

Result:

- Score: 92-99 depending on alias confidence.
- Status: `matched` if score is at or above automatic threshold.
- Method: `alias`

Alias matches are critical because market staff often use shorthand names.

### 3. Barcode Match

If barcode is present, compare against `Product.barcode`.

Result:

- Score: 100 for unique barcode.
- Status: `matched`.
- Method: `barcode`.

If duplicate barcode exists, return candidates for review.

### 4. Fuzzy Match

Compare normalized incoming name with product names, short names, and aliases using token similarity.

Recommended MVP checks:

- Token overlap.
- Levenshtein or trigram similarity.
- Brand token match.
- Package size match.
- Category hint match if parsed.

Result:

- Score based on weighted model.
- Top candidates stored as `MatchingSuggestion`.

### 5. AI-Assisted Normalization

Later, AI can suggest normalized product names, brands, package sizes, and ambiguous candidates.

Rules:

- AI output is a suggestion, not final truth.
- AI cannot override an approved manual match.
- AI must return structured JSON.
- Keep model/provider details behind a `ParsingAssistant` or `MatchingAssistant` service.

## Confidence Thresholds

Recommended defaults:

- `>= 90`: auto-match.
- `70-89`: low confidence, needs review.
- `< 70`: not found unless there is a strong barcode match.

Per-market settings can override later, but MVP should use one global setting.

## Simple Scoring Model

Use a deterministic score from 0 to 100:

| Signal | Weight | Notes |
|---|---:|---|
| Exact normalized name | 40 | Full match receives all points |
| Alias match | 30 | Manual alias receives stronger confidence |
| Brand match | 10 | Brand token or parsed brand |
| Package size match | 10 | Example: `2L`, `400g`, `10lu` |
| Category hint match | 5 | If incoming text or prior market history suggests category |
| Barcode match | Override | Unique barcode sets score to 100 |
| Penalty: conflicting package size | -25 | Example: incoming 1L vs product 2L |
| Penalty: inactive product | -15 | Still show as suggestion |

Example:

```txt
Incoming: Ulker Halley 10lu
Candidate: Ulker Halley 10'lu
Name similarity: 36/40
Brand: 10/10
Package size: 10/10
Alias: 25/30
Total: 81/100 -> low_confidence or matched depending on alias confidence
```

## Match Statuses

| Status | Meaning |
|---|---|
| `matched` | Safe automatic match |
| `low_confidence` | Candidate exists but user/operator should review |
| `not_found` | No reliable candidate |
| `manual_selected` | User/operator chose a product |
| `new_product_needed` | Product should be created |

## Missing Product Resolution

For each unresolved campaign item, support these actions:

### Manual Match

User selects an existing product.

Backend actions:

- Set `product_id`.
- Set `match_status = manual_selected`.
- Set `match_method = manual`.
- Optionally create a `ProductAlias` from incoming name after user confirms.

### New Product Creation

User creates a market-specific product from the campaign item.

Backend actions:

- Create `Product` scoped to market.
- Create initial `ProductAlias` using incoming name.
- Link campaign item to new product.
- Mark item `manual_selected` or `matched`.

### Use Without Image

User allows a text-only product card.

Backend actions:

- Set `use_without_image = true`.
- Keep `product_id` nullable if no product exists.
- Require template renderer to support text-only fallback.

### Exclude From Campaign

User removes the item from output without deleting history.

Backend actions:

- Set `excluded = true`.
- Keep raw text and parse result.
- Recalculate campaign counts.

## Learning From Manual Work

MVP should learn only simple deterministic data:

- Manual match can create a product alias.
- Repeated incoming name can increase alias confidence.
- Rejected suggestions should be stored to avoid repeating poor candidates later.

Do not implement model training in MVP.
