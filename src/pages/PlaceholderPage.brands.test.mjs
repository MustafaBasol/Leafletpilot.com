import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const page = readFileSync(new URL("./PlaceholderPage.jsx", import.meta.url), "utf8");

test("the 'Global kayıt' checkbox never renders on the Brands form (categories keep it, brands do not)", () => {
  assert.match(page, /\{!isBrand \? \(\s*<label className="check-row">/);
});

test("brand create payload never sends is_global from the market UI, regardless of form state", () => {
  assert.match(page, /is_global: isBrand \? false : form\.isGlobal/);
});

test("a duplicate/normalized-match brand name surfaces guidance instead of a bare error", () => {
  assert.match(page, /duplicateSuggestion/);
  assert.match(page, /Bu marka zaten mevcut: <strong>\{duplicateSuggestion\.name\}<\/strong>\. Bunu mu demek istediniz\?/);
});

test("edit action is hidden for global brands, matching the backend's rejection of global edits", () => {
  assert.match(page, /item\.is_global \? \(/);
});
