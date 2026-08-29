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

test("Campaign Detail uses the server-resolved effective image with accessible thumbnail fallback", () => {
  assert.match(dataSource, /effective_image_url/);
  assert.match(dataSource, /image: Boolean\(item\.effective_image_url\)/);
  assert.match(page, /imageUrl=\{product\.effectiveImageUrl\}/);
  assert.match(page, /refreshKey=\{product\.effectiveImageRefreshKey\}/);
  assert.match(page, /alt=\{product\.matchedProduct \|\| product\.incomingName\}/);
  assert.match(page, /marketId=\{campaign\.marketId\}/);
});
test("an explicit ?view=preview request scrolls to and focuses the real preview section", () => {
  assert.match(page, /export function CampaignDetail\(\{ campaignId, view = "" \}\)/);
  assert.match(page, /if \(view !== "preview" \|\| isLoading\) return;/);
  assert.match(page, /previewSectionRef\.current/);
  assert.match(page, /node\.scrollIntoView\(\{ behavior: "smooth", block: "start" \}\)/);
  assert.match(page, /node\.focus\(\{ preventScroll: true \}\)/);
  assert.match(page, /id="campaign-preview-section"[\s\S]*ref=\{previewSectionRef\}[\s\S]*tabIndex=\{-1\}/);
});

test("campaign intelligence is inspectable before explicit application", () => {
  assert.match(api, /intelligence\/analyze/);
  assert.match(api, /intelligence\/apply/);
  assert.match(dataSource, /analyzeCampaignIntelligence/);
  assert.match(dataSource, /applyCampaignIntelligence/);
  assert.match(page, /campaign-intelligence-analyze/);
  assert.match(page, /campaign-intelligence-apply/);
  assert.match(page, /intelligence\.warnings/);
  assert.match(page, /product\.reasons\.slice/);
  assert.match(styles, /\.intelligence-panel/);
});

test("Campaign Detail sends structured versioned revisions and refreshes after conflicts", () => {
  assert.match(api, /applyCampaignRevision/);
  assert.match(api, /undoCampaignRevision/);
  assert.match(api, /approveCampaign/);
  assert.match(dataSource, /rawPrice: item\.price/);
  assert.match(dataSource, /draftRevision: campaign\.draft_revision/);
  assert.match(page, /client_request_id: revisionRequestId/);
  assert.match(page, /expected_revision: campaign\.draftRevision/);
  assert.match(page, /Taslak başka bir işlemle güncellendi/);
  assert.match(page, /await loadPreview\(\)/);
});

test("Campaign Detail exposes deterministic draft controls without catalog mutation UI", () => {
  assert.match(page, /Taslak sürümü/);
  assert.match(page, /Son değişikliği geri al/);
  assert.match(page, /Taslağı Onayla/);
  assert.match(page, /type: "move_item"/);
  assert.match(page, /type: "remove_item"/);
  assert.match(page, /type: "restore_item"/);
  assert.match(page, /type: "update_price"/);
  assert.match(page, /type: "update_display_name"/);
  assert.match(page, /type: "set_hero"/);
  assert.match(page, /type: "set_item_emphasis"/);
  assert.match(page, /type: "replace_image"/);
  assert.match(page, /yalnızca bu broşür taslağına uygulanır; katalog ürünü değişmez/);
});


test("approval sends the displayed revision and refreshes a stale approval without retrying", () => {
  assert.match(page, /approveCampaign\(campaignId, campaign\.draftRevision \?\? 0\)/);
  assert.match(api, /approveCampaign\(campaignId, payload, marketId\)/);
  assert.match(dataSource, /expected_revision: expectedRevision/);
  assert.match(page, /Güncel sürümü inceleyip yeniden onaylayın/);
  assert.doesNotMatch(page, /source: "panel"/);
});

test("visible-only reordering skips hidden rows and uses backend visible positions", () => {
  assert.match(page, /const visibleItems = rows\.filter\(\(row\) => !row\.isHidden\)/);
  assert.match(page, /const targetPosition = visibleIndex \+ direction \+ 1/);
  assert.match(page, /target_position: targetPosition/);
  assert.match(page, /visibleRows\.findIndex/);
  assert.doesNotMatch(page, /target_position: index \+ direction \+ 1/);
});

test("AI revision is an explicit proposal and confirmation flow", () => {
  assert.match(api, /createAIRevisionProposal/);
  assert.match(api, /applyAIRevisionProposal/);
  assert.match(dataSource, /createAIRevisionProposal/);
  assert.match(dataSource, /applyAIRevisionProposal/);
  assert.match(page, /Ne değiştirmek istiyorsunuz\?/);
  assert.match(page, /onSubmit=\{prepareAIRevision\}/);
  assert.match(page, /Öneriyi Hazırla/);
  assert.match(page, /aiProposal\.status === "ready"/);
  assert.match(page, /aiProposal\.status === "clarification_required"/);
  assert.match(page, /aiProposal\.status === "unsupported"/);
  assert.match(page, /applyAIRevisionProposal\(campaignId, aiProposal\.id\)/);
  assert.match(page, /setAiProposal\(null\)/);
  assert.match(styles, /\.ai-revision-proposal/);
});

test("AI is not called on keystrokes, page load, preview refresh, or manual revisions", () => {
  assert.match(page, /onChange=\{\(event\) => setAiInstruction\(event\.target\.value\)\}/);
  assert.doesNotMatch(page, /onChange=\{[^}]*createAIRevisionProposal/);
  assert.doesNotMatch(page, /useEffect\([^)]*createAIRevisionProposal/);
  assert.doesNotMatch(page, /loadPreview[\s\S]{0,200}createAIRevisionProposal/);
  assert.doesNotMatch(page, /runDraftRevision[\s\S]{0,300}createAIRevisionProposal/);
});

test("AI proposal conflicts refresh authoritative campaign and preview state", () => {
  assert.match(page, /if \(error\.status === 409\)/);
  assert.match(page, /setAiProposal\(null\);[\s\S]*await loadCampaign\(\);[\s\S]*await loadPreview\(\)/);
  assert.match(page, /proposal_expired/);
  assert.match(page, /stale_revision/);
});

test("failed AI professionalization exposes safe retry actions", () => {
  assert.match(page, /Üretim tamamlanamadı/);
  assert.match(page, />Tekrar Dene</);
  assert.match(page, />Talimatla Tekrar Dene</);
  assert.match(page, /professionalizationFailureMessage\(latest\.failure_reason\)/);
  assert.match(page, /Orijinal onaylı broşür kullanılmaya devam ediyor/);
  assert.doesNotMatch(page, /setProfessionalizationError\(error\.message/);
});

test("visual revision uses the retry API with instruction and ready-source lineage", () => {
  assert.match(api, /professionalization\/retry/);
  assert.match(dataSource, /retryProfessionalization/);
  assert.match(page, /client_request_id: revisionRequestId\("professionalization"\)/);
  assert.match(page, /instruction: instruction\.trim\(\) \|\| null/);
  assert.match(page, /source_run_id: sourceRunId/);
  assert.match(page, />Yeniden Düzenle</);
  assert.match(page, /AI tasarımını yeniden düzenle/);
  assert.match(page, /Neyi değiştirmek istersiniz\?/);
  assert.match(page, /maxLength=\{500\}/);
  assert.match(page, /Ürün, fiyat ve kampanya bilgileri değiştirilemez/);
  assert.match(page, /Yeniden Oluştur/);
});

test("ready versions support view, explicit selection, original fallback, and history", () => {
  assert.match(page, /AI Tasarımını Görüntüle/);
  assert.match(page, /AI Tasarımını Kullan/);
  assert.match(page, /applyProfessionalizationRun\(campaignId, run\.id\)/);
  assert.match(page, /restoreOriginalProfessionalization\(campaignId\)/);
  assert.match(page, />Orijinale Dön</);
  assert.match(page, /AI tasarım sürüm geçmişi/);
  assert.match(page, /Seçili AI sürümü \{active\.version_number\} kullanılmaya devam ediyor/);
});