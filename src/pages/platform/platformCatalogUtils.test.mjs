import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { normalizeOptionalUuid, revokeObjectUrls } from "./platformCatalogUtils.js";

test("normalizes empty catalog selections to null UUID values", () => {
  assert.equal(normalizeOptionalUuid(""), null);
  assert.equal(normalizeOptionalUuid(null), null);
  assert.equal(normalizeOptionalUuid("7f2a"), "7f2a");
});

test("revokes each object URL once, including duplicate references", () => {
  const revoked = [];
  const original = URL.revokeObjectURL;
  URL.revokeObjectURL = (url) => revoked.push(url);
  try {
    revokeObjectUrls({ first: "blob:first", second: "blob:first", third: "blob:third" });
  } finally {
    URL.revokeObjectURL = original;
  }
  assert.deepEqual(revoked.sort(), ["blob:first", "blob:third"]);
});

const editorSource = await readFile("src/pages/platform/PlatformCatalog.jsx", "utf8");
test("manual upload keeps the selected preview on failure and reports the saved trusted status", () => {
  assert.match(editorSource, /catch \(err\) \{ setError\(imageUploadErrorText\(err\)\); \}/);
  assert.match(editorSource, /Görsel kaydedildi\./);
  assert.match(editorSource, /await refreshProduct\(\); setReplaceTarget\(null\); setNotice\("Görsel kaydedildi\."\)/);
  assert.match(editorSource, /"Image content is invalid or corrupt\.": "Seçilen dosya geçerli bir PNG\/JPEG\/WebP görseli değil\."/);
  assert.match(editorSource, /qualityStatusLabels = \{ excellent: "Onaylandı", good: "Onaylandı"/);
  assert.doesNotMatch(editorSource, /Görsel yüklendi ve incelemeye gönderildi/);
});
