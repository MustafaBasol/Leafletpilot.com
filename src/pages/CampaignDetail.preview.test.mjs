import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const page = readFileSync(new URL("./CampaignDetail.jsx", import.meta.url), "utf8");
const fileCard = readFileSync(new URL("../components/ui/FileCard.jsx", import.meta.url), "utf8");
const api = readFileSync(new URL("../api/campaignApi.js", import.meta.url), "utf8");
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
  assert.match(page, /Math\.min\(rect\.width \/ 1240, rect\.height \/ 1754\)/);
});
