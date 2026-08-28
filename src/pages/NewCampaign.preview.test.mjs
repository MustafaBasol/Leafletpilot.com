import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { getCampaignPreviewDimensions } from "../components/ui/campaignPreviewSizing.js";

const page = readFileSync(new URL("./NewCampaign.jsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");
const app = readFileSync(new URL("../App.jsx", import.meta.url), "utf8");

test("template gallery uses inert scaled thumbnails", () => {
  assert.match(page, /template-thumbnail/);
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

test("smart composition defaults on for new campaigns and preserves legacy drafts", () => {
  assert.ok(page.includes("smart_composition: true"));
  assert.ok(page.includes("smart_composition: false"));
  assert.ok(page.includes("Smart composition"));
  assert.ok(page.includes("event.target.checked"));
  assert.ok(page.includes("builder_config: { ...builderConfig, output_format: format }"));
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

test("campaign product thumbnails use deterministic authenticated image cache keys", () => {
  assert.match(page, /imageUrl=\{product\.image_url\}/);
  assert.match(page, /refreshKey=\{product\.image_url\}/);
  assert.doesNotMatch(page, /refreshKey=\{(?:Math\.random|Date\.now)/);
});

test("saved drafts and frozen campaign revisions reopen in the shared builder", () => {
  assert.match(app, /sourceCampaignId=\{new URLSearchParams\(search\)\.get\("source"\)/);
  assert.match(app, /editCampaignId=\{pathname\.slice\("/);
  assert.match(page, /campaignToLoad \? getCampaign\(campaignToLoad, selectedMarketId\)/);
  assert.match(page, /setCampaignId\(isRevision \? "" : loadedCampaign\.id\)/);
  assert.match(page, /window\.location\.hash = `#\/campaigns\/\$\{id\}\/edit`/);
  assert.match(page, /Önceki kampanya yeni bir revizyon olarak yüklendi/);
});


test("full campaign previews fit backend-declared portrait and landscape pages without gallery transforms", () => {
  assert.deepEqual(
    getCampaignPreviewDimensions('<body data-preview-width="1240" data-preview-height="1754">', "pdf"),
    { width: 1240, height: 1754 },
  );
  assert.deepEqual(
    getCampaignPreviewDimensions('<body data-preview-width="1754" data-preview-height="1240">', "pdf"),
    { width: 1754, height: 1240 },
  );
  assert.match(page, /CampaignHtmlPreview html=\{preview\.html\}/);
  assert.match(page, /typeof response\?\.html !== "string" \|\| !response\.html\.trim\(\)/);
  assert.doesNotMatch(page, /className="campaign-preview-frame"/);
  assert.doesNotMatch(styles, /\.campaign-preview-frame\s*\{[\s\S]*transform: scale\(0\.5\)/);
  assert.match(styles, /template-gallery-card iframe[\s\S]*transform: scale\(0\.2\)/);
});
