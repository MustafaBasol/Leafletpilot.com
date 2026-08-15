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
test("single save owns image upload and retains preview on partial failure", () => {
  assert.match(editorSource, /const saveProduct = async/);
  assert.match(editorSource, /await platformApi\.uploadGlobalProductImage\(saved\.id, file/);
  assert.match(editorSource, /Ürün bilgileri kaydedildi ancak görsel yüklenemedi:/);
  assert.match(editorSource, /className="visually-hidden" type="file"/);
  assert.match(editorSource, /Ürünü Kaydet/);
  assert.doesNotMatch(editorSource, /Görseli yükle/);
  assert.doesNotMatch(editorSource, /Choisir un fichier/);
  assert.match(editorSource, /quality_status === "needs_review"/);
});

const bulkImageModalSource = await readFile("src/pages/platform/PlatformBulkImageImportModal.jsx", "utf8");
test("bulk image import uses the trusted Turkish footer workflow", () => {
  assert.match(bulkImageModalSource, /className="visually-hidden" type="file"/);
  assert.match(bulkImageModalSource, /import \{ Button \}/);
  assert.match(bulkImageModalSource, /Paketi Analiz Et/);
  assert.match(bulkImageModalSource, /görseli yükle/);
  assert.match(bulkImageModalSource, /Önizleme özeti/);
  assert.match(bulkImageModalSource, /catalog-import-table bulk-image-preview-table/);
  assert.match(bulkImageModalSource, /global katalogda kullanıma hazır/);
  assert.doesNotMatch(bulkImageModalSource, /Choisir un fichier|Analyze package|Confirm import|Upload a products\.zip|<button/);
});
