import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const page = readFileSync(new URL("./Templates.jsx", import.meta.url), "utf8");
const builder = readFileSync(new URL("../components/templates/TemplateBuilderModal.jsx", import.meta.url), "utf8");
const detail = readFileSync(new URL("./TemplateDetail.jsx", import.meta.url), "utf8");
const api = readFileSync(new URL("../api/templateApi.js", import.meta.url), "utf8");

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

test("builder resets only when the create or edit target changes", () => {
  assert.match(builder, /const targetKey = template\?\.id \? `edit:\$\{template\.id\}` : "create"/);
  assert.match(builder, /useMemo\(\(\) => buildInitialForm\(template\), \[targetKey\]\)/);
  assert.match(builder, /setForm\(initial\);\s*setSubmitted\(false\);/);
  assert.doesNotMatch(builder, /\}, \[template\]\)/);
});

test("template detail gates editing for permissions and global templates", () => {
  assert.match(detail, /const canEdit = canManage && !template\.isGlobal/);
  assert.match(detail, /if \(!canEdit \|\| isSaving\) return/);
  assert.match(detail, /if \(canEdit\) setEditing\(true\)/);
  assert.match(detail, /\{canEdit && isEditing \? <TemplateBuilderModal/);
});

test("thumbnail upload falls back when the browser omits the file content type", () => {
  assert.match(api, /file\.type \|\| "application\/octet-stream"/);
});

test("global and market template previews use the hash-based SPA detail route", () => {
  assert.doesNotMatch(page, /window\.location\.href\s*=\s*`\/templates\//);
  const previewLinks = page.match(/<Button href=\{`#\/templates\/\$\{template\.id\}`\}>Önizle<\/Button>/g) || [];
  assert.equal(previewLinks.length, 2);
});
