import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const page = readFileSync(new URL("./Templates.jsx", import.meta.url), "utf8");
const builder = readFileSync(new URL("../components/templates/TemplateBuilderModal.jsx", import.meta.url), "utf8");

test("create opens a form without posting and submission is guarded", () => {
  assert.match(page, /setBuilderTemplate\(null\)/);
  assert.match(page, /submittingRef\.current/);
  assert.doesNotMatch(page, /name: "Yeni özel şablon"/);
  assert.match(builder, /onSubmit=\{submit\}/);
  assert.match(builder, /Şablon adı zorunludur/);
});

test("builder exposes canonical settings, preview, dirty warning, and duplicate feedback", () => {
  for (const key of ["layout", "columns", "rows", "slot_count", "page_format", "primary_color", "secondary_color", "price_style", "badge_style", "show_footer"]) assert.match(builder, new RegExp(key));
  assert.match(builder, /template-live-preview/);
  assert.match(builder, /beforeunload/);
  assert.match(builder, /Kaydedilmemiş değişiklikler/);
  assert.match(page, /Bu isimle bir şablon zaten mevcut/);
});
