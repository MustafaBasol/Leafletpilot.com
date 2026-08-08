import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const page = readFileSync(new URL("./CampaignDetail.jsx", import.meta.url), "utf8");
const fileCard = readFileSync(new URL("../components/ui/FileCard.jsx", import.meta.url), "utf8");
const api = readFileSync(new URL("../api/campaignApi.js", import.meta.url), "utf8");
const dataSource = readFileSync(new URL("../data/dataSource.js", import.meta.url), "utf8");
const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

test("authenticated PDF and PNG previews use the scoped file endpoint", () => {
  assert.match(api, /fetchCampaignFile/);
  assert.match(api, /Authorization: `Bearer \$\{token\}`/);
  assert.match(api, /X-Market-Id/);
  assert.match(page, /fetchCampaignFile\(campaignId, file\.id/);
  assert.match(page, /URL\.createObjectURL/);
  assert.match(page, /URL\.revokeObjectURL/);
  assert.match(page, /application\/pdf/);
});

test("preview controls are bounded, loading-aware, and ignore non-ready files", () => {
  assert.match(fileCard, /file\.rawStatus === "ready"/);
  assert.match(fileCard, /isPreviewing/);
  assert.match(page, /previewZoom <= 0\.5/);
  assert.match(page, /previewZoom >= 2/);
  assert.match(page, /ResizeObserver/);
});

test("fit mode preserves A4 ratio and only enables scrolling after manual zoom", () => {
  assert.match(styles, /aspect-ratio: 210 \/ 297/);
  assert.match(styles, /overflow: hidden/);
  assert.match(styles, /\.campaign-preview-viewport\.is-zoomed[\s\S]*overflow: auto/);
  assert.match(page, /Math\.min\(availableWidth \/ PREVIEW_PAGE_WIDTH, availableHeight \/ PREVIEW_PAGE_HEIGHT\)/);
  assert.match(page, /campaign-preview-page-box/);
  assert.match(page, /width: PREVIEW_PAGE_WIDTH \* fitScale \* previewZoom/);
  assert.match(page, /previewMode === "manual"/);
  assert.match(page, /Math\.round\(fitScale \* previewZoom \* 100\)/);
});

test("fit reset and resize use the viewport rather than the adjacent grid panel", () => {
  assert.match(page, /observer\.observe\(element\)/);
  assert.match(page, /setPreviewMode\("fit"\)/);
  assert.match(page, /setPreviewZoom\(1\)/);
  assert.match(styles, /\.campaign-preview-page-box[\s\S]*flex: 0 0 auto/);
});

test("preview remeasurement is reused without synthetic resize events", () => {
  assert.match(page, /const measurePreview = useCallback/);
  assert.match(page, /new ResizeObserver\(measurePreview\)/);
  assert.match(page, /window\.addEventListener\("resize", measurePreview\)/);
  assert.match(page, /requestAnimationFrame\(measurePreview\)/);
  assert.doesNotMatch(page, /dispatchEvent\(new Event\("resize"\)\)/);
});

test("frozen campaigns expose a revision route and hide rejected mutation actions", () => {
  assert.match(page, /const canMutateCurrentCampaign = canEditCampaigns && !campaign\.frozenAt/);
  assert.match(page, /campaign\.frozenAt \? `#\/campaigns\/new\?source=\$\{campaignId\}` : `#\/campaigns\/\$\{campaignId\}\/edit`/);
  assert.match(page, /campaign\.frozenAt \? "Yeni Revizyon Oluştur" : "Broşürü Düzenle"/);
  assert.match(page, /canMutateCurrentCampaign \? <MissingProductModal/);
});

test("failed export jobs surface an error instead of a success notice", () => {
  assert.match(dataSource, /if \(job\?\.status === "failed"\)/);
  assert.match(dataSource, /throw new Error\(job\.error_message \|\| "Çıktı üretilemedi/);
});
