import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  candidateProducts,
  catalogQualitySeverityLabel,
  catalogQualityStateLabel,
  mergeSelection,
  readableQualityItems,
} from "./catalogQualityUtils.js";

test("catalog quality helpers expose stable Turkish review labels and canonical winner selection", () => {
  const candidate = { product_a: { id: "a", name: "Kaynak" }, product_b: { id: "b", name: "Hedef" } };
  assert.equal(catalogQualityStateLabel("barcode_conflict"), "Barkod çakışması");
  assert.equal(catalogQualitySeverityLabel("high"), "Yüksek");
  assert.deepEqual(candidateProducts(candidate), { productA: candidate.product_a, productB: candidate.product_b });
  assert.deepEqual(mergeSelection(candidate, "b"), { sourceId: "a", targetId: "b" });
  assert.deepEqual(mergeSelection(candidate, "a"), { sourceId: "b", targetId: "a" });
  assert.deepEqual(readableQualityItems({ aliases: 2, images: 0 }), ["aliases: 2"]);
});

test("catalog quality UI renders candidates, preview, explicit confirmation, ignore, and refreshes after merge", async () => {
  const source = await readFile("src/pages/platform/CatalogQualityPanel.jsx", "utf8");
  assert.match(source, /listCatalogQualityCandidates/);
  assert.match(source, /Karşılaştır/);
  assert.match(source, /Etki önizlemesi/);
  assert.match(source, /Korunacak kanonik ürün/);
  assert.match(source, /Birleştirmeyi Onayla/);
  assert.match(source, /Aynı ürün değil/);
  assert.match(source, /previewCatalogProductMerge/);
  assert.match(source, /mergeCatalogProducts/);
  assert.match(source, /ignoreCatalogQualityCandidate/);
  assert.match(source, /Birleştirmeyi engelleyen durumlar/);
  assert.match(source, /await load\(0\)/);
});

test("platform catalog exposes the quality tab through the platform API adapter", async () => {
  const [catalogSource, apiSource] = await Promise.all([
    readFile("src/pages/platform/PlatformCatalog.jsx", "utf8"),
    readFile("src/api/platformApi.js", "utf8"),
  ]);
  assert.match(catalogSource, /CatalogQualityPanel/);
  assert.match(catalogSource, /quality: "Veri Kalitesi"/);
  assert.match(apiSource, /\/platform\/catalog\/quality\/candidates/);
  assert.match(apiSource, /\/platform\/catalog\/quality\/merge-preview/);
  assert.match(apiSource, /\/platform\/catalog\/quality\/merge/);
  assert.match(apiSource, /\/platform\/catalog\/quality\/ignore/);
});