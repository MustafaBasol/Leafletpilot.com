import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const modalSource = await readFile("src/pages/platform/PlatformMarketProductImportModal.jsx", "utf8");

test("market catalog import modal uses the preview-then-commit contract", () => {
  assert.match(modalSource, /platformApi\.previewMarketProductImport\(marketId, file\)/);
  assert.match(modalSource, /platformApi\.commitMarketProductImport\(marketId, preview\.import_id, overrides\)/);
  assert.match(modalSource, /platformApi\.downloadMarketProductImportTemplate\(marketId\)/);
});

test("ambiguous rows require an explicit candidate selection, not a silent auto-pick", () => {
  assert.match(modalSource, /global_ambiguous/);
  assert.match(modalSource, /candidates\.map\(\(candidate\)/);
  assert.doesNotMatch(modalSource, /candidates\[0\]/);
});

test("blocked row states never render a default action control", () => {
  assert.match(modalSource, /BLOCKED_STATES = new Set\(\["invalid", "duplicate_in_file", "conflict", "global_ambiguous"\]\)/);
});

test("quota projection surfaces a warning when the plan limit would be exceeded", () => {
  assert.match(modalSource, /quota\?\.would_exceed/);
  assert.match(modalSource, /Plan kotası aşılacak/);
});

test("existing market products default to update, not silent overwrite of another field", () => {
  assert.match(modalSource, /existing_market_product/);
  assert.match(modalSource, /Güncelle/);
  assert.match(modalSource, /Atla/);
});

test("uses the shared Modal/Button primitives, no bespoke dialog markup", () => {
  assert.match(modalSource, /import \{ Button \} from "\.\.\/\.\.\/components\/ui\/Button\.jsx"/);
  assert.match(modalSource, /import \{ Modal \} from "\.\.\/\.\.\/components\/ui\/Modal\.jsx"/);
});

const marketDetailSource = await readFile("src/pages/platform/PlatformMarketDetail.jsx", "utf8");
test("market detail page wires the import modal behind a trigger button", () => {
  assert.match(marketDetailSource, /import \{ PlatformMarketProductImportModal \}/);
  assert.match(marketDetailSource, /showImportModal/);
  assert.match(marketDetailSource, /<PlatformMarketProductImportModal/);
  assert.match(marketDetailSource, /onImported=\{load\}/);
});
