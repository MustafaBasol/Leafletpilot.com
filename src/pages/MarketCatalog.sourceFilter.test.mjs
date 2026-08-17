import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const page = readFileSync(new URL("./MarketCatalog.jsx", import.meta.url), "utf8");

test("global_override is kept as a real, distinct source state (not merged into 'Tüm kaynaklar')", () => {
  assert.match(page, /function sourceState\(item\)/);
  assert.match(page, /\["global", "local", "global_override"\]\.includes\(item\.source_state\)/);
});

test("global_override's customer-facing label was renamed away from the confusing 'Global + Market Düzenlemesi'", () => {
  assert.match(page, /state === "global_override".*return "Market Tarafından Düzenlenmiş"/);
  assert.doesNotMatch(page, /Global \+ Market Düzenlemesi/);
});

test("the source filter actually narrows visibleMine by the selected source state", () => {
  assert.match(page, /source === "all" \|\| sourceState\(item\) === source/);
});

test("the shared ('Globalden ürün ekle') tab auto-searches on typing via a debounced effect, not only on an Ara click", () => {
  const sharedEffectStart = page.indexOf("SEARCH_DEBOUNCE_MS");
  assert.notEqual(sharedEffectStart, -1, "expected a debounce constant for the shared-tab search effect");
  assert.match(page, /window\.setTimeout\(\(\) => \{ loadShared\(\); \}, SEARCH_DEBOUNCE_MS\)/);
});

test("the redundant 'Ara' button was removed now that both tabs auto-search", () => {
  assert.doesNotMatch(page, />\s*Ara\s*<\/(button|Button)>/);
});
