import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const page = readFileSync(new URL("./NewCampaign.jsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

test("template gallery uses inert scaled thumbnails", () => {
  assert.match(page, /template-thumbnail/);
  assert.match(page, /scrolling="no"/);
  assert.match(styles, /template-gallery-card iframe[\s\S]*pointer-events: none/);
  assert.match(styles, /transform: scale\(0\.2\)/);
});

test("preview refresh persists metadata and guards stale responses", () => {
  assert.match(page, /builderConfig\.headline/);
  assert.match(page, /builderConfig\.subtitle/);
  assert.match(page, /builderConfig\.footer/);
  assert.match(page, /cache_bust: requestId/);
  assert.match(page, /previewRequestRef\.current/);
  assert.match(page, /previewLoading/);
  assert.match(page, /previewError/);
});

test("preview formats expose real aspect variants", () => {
  for (const id of ["instagram_post", "instagram_story", "whatsapp"]) assert.match(page, new RegExp(id));
  assert.match(styles, /preview-format-instagram_post/);
  assert.match(styles, /preview-format-instagram_story/);
});

test("product selection uses a compact accessible mode selector and full-width grid", () => {
  assert.match(page, /product-mode-selector/);
  assert.match(page, /role="tablist"/);
  assert.match(page, /aria-selected=\{inputMode === "catalog"\}/);
  assert.match(page, /product-grid/);
  assert.match(styles, /grid-template-columns: repeat\(4, minmax\(0, 1fr\)\)/);
  assert.match(styles, /grid-template-columns: repeat\(5, minmax\(0, 1fr\)\)/);
});

test("catalog selection supports search, filters, keyboard-safe card semantics, and clear", () => {
  assert.match(page, /type="search"/);
  assert.match(page, /productCategory/);
  assert.match(page, /productBrand/);
  assert.match(page, /aria-pressed=\{checked\}/);
  assert.match(page, /onClick=\{\(\) => toggleProduct\(product\)\}/);
  assert.match(page, /clearSelectedProducts/);
  assert.match(page, /selectedProducts\.length/);
  assert.match(page, /disabled=\{isBusy \|\| !selectedProducts\.length \|\| slotValidation\}/);
  assert.match(page, /product-card-check/);
});

test("catalog loading, empty, error, and no-result states are present without changing active-product filtering", () => {
  assert.match(page, /builderLoading/);
  assert.match(page, /builderLoadError/);
  assert.match(page, /Tekrar dene/);
  assert.match(page, /Bu markette aktif ürün yok/);
  assert.match(page, /Sonuç bulunamadı/);
  assert.match(page, /product\.is_active !== false/);
});

test("text import remains available and selection summary has thumbnails", () => {
  assert.match(page, /Metin listesi içe aktar/);
  assert.match(page, /parseText/);
  assert.match(page, /selection-summary/);
  assert.match(page, /selectedProducts\.slice\(0, 5\)/);
  assert.match(page, /Tümünü temizle/);
});
