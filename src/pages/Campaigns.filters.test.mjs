import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const page = readFileSync(new URL("./Campaigns.jsx", import.meta.url), "utf8");
const dataSource = readFileSync(new URL("../data/dataSource.js", import.meta.url), "utf8");

test("Durum, Kanal, Tarih and Eksik ürün filters are real controls wired into the fetch", () => {
  assert.match(page, /<FilterSelect label="Durum" value=\{filters\.status\}/);
  assert.match(page, /<FilterSelect label="Kanal" value=\{filters\.channel\}/);
  assert.match(page, /<FilterSelect label="Tarih" value=\{filters\.date\}/);
  assert.match(page, /label="Eksik ürün"[\s\S]*value=\{filters\.missing\}/);
  assert.match(page, /status: filters\.status === "all" \? undefined : filters\.status/);
  assert.match(page, /channel: filters\.channel === "all" \? undefined : filters\.channel/);
  assert.match(page, /hasMissingProducts: filters\.missing === "all" \? undefined : filters\.missing === "yes"/);
});

test("Market filter chip was deliberately dropped (page is single-market-scoped)", () => {
  assert.doesNotMatch(page, /FilterSelect label="Market"/);
  assert.doesNotMatch(page, /<FilterChip label="Market"/);
});

test("filters compose together (all active filter keys feed the same fetch call)", () => {
  const loadEffect = page.slice(page.indexOf("async function loadCampaigns"), page.indexOf("loadCampaigns();"));
  assert.match(loadEffect, /search: debouncedSearch \|\| undefined/);
  assert.match(loadEffect, /status: filters\.status/);
  assert.match(loadEffect, /channel: filters\.channel/);
  assert.match(loadEffect, /dateFrom: dateFromForPreset\(filters\.date\)/);
  assert.match(loadEffect, /hasMissingProducts: filters\.missing/);
  assert.match(page, /\[selectedMarketId, debouncedSearch, filters\.status, filters\.channel, filters\.date, filters\.missing\]/);
});

test("search is debounced rather than firing on every keystroke", () => {
  assert.match(page, /setTimeout\(\(\) => setDebouncedSearch\(searchTerm\.trim\(\)\), 350\)/);
  assert.match(page, /onSearchChange=\{\(event\) => setSearchTerm\(event\.target\.value\)\}/);
});

test("a reset control clears filters and search back to defaults", () => {
  assert.match(page, /function resetFilters\(\)/);
  assert.match(page, /setFilters\(defaultFilters\)/);
  assert.match(page, /setSearchTerm\(""\)/);
  assert.match(page, /hasActiveFilters/);
});

test("backend query building maps camelCase filters onto the real API params, including has_missing_products", () => {
  assert.match(dataSource, /const \{ search, status, channel, dateFrom, dateTo, hasMissingProducts, limit = 50, offset = 0 \} = filters/);
  assert.match(dataSource, /has_missing_products: hasMissingProducts === undefined \? undefined : hasMissingProducts/);
  assert.match(dataSource, /date_from: dateFrom \|\| undefined/);
  assert.match(dataSource, /date_to: dateTo \|\| undefined/);
});

test("Önizleme and Yeniden Oluştur route to real workflows, not dead buttons", () => {
  assert.match(page, /href=\{`#\/campaigns\/\$\{campaign\.id\}`\}[\s\S]*Detay/);
  assert.match(page, /onClick=\{\(\) => setRegenerateTarget\(campaign\)\}/);
  assert.match(page, /await regenerateCampaignPreview\(campaign\.id\)/);
  assert.match(page, /REGENERATE_BLOCKED_STATUSES = new Set\(\["draft", "parsing", "matching", "cancelled"\]\)/);
});

test("Önizleme explicitly requests preview mode instead of the generic detail route", () => {
  assert.match(page, /href=\{`#\/campaigns\/\$\{campaign\.id\}\?view=preview`\}[\s\S]{0,80}Önizleme/);
});
