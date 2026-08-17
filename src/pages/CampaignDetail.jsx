import { useCallback, useEffect, useRef, useState } from "react";
import { canCreateExports, canMutateCampaigns, getSelectedMarketId } from "../api/authSession.js";
import { isRealApiEnabled } from "../api/config.js";
import { campaignProducts, findCampaignById, generatedFiles } from "../data/mockData.js";
import {
  createCampaignExportJob,
  analyzeCampaignIntelligence,
  applyCampaignIntelligence,
  downloadCampaignFile,
  finalizeCampaign,
  generateCampaignDetailSuggestions,
  generateCampaignItemSuggestions,
  getCampaignDetail,
  getCampaignPreviewHtml,
  fetchCampaignFile,
  resolveCampaignItem,
  reorderCampaignItems,
  updateCampaignDetail,
} from "../data/dataSource.js";
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  ExportPanel,
  MissingProductModal,
  Modal,
  PageHeader,
  PreviewFrame,
  ProductThumbnail,
  StatusBadge,
  Table,
} from "../components/ui/index.js";

function scoreTone(score) {
  if (score >= 90) return "success";
  if (score >= 75) return "warning";
  return "danger";
}

function needsAttention(status) {
  return ["Kontrol gerekli", "Bulunamadı", "Yeni ürün gerekli", "Görselsiz devam"].includes(status);
}

const fileStatusLabels = {
  pending: "Bekliyor",
  generating: "Oluşturuluyor",
  ready: "Hazır",
  failed: "Başarısız",
  sent: "Gönderildi",
};

const exportJobStatusLabels = {
  queued: "Kuyrukta",
  running: "Çalışıyor",
  completed: "Tamamlandı",
  failed: "Başarısız",
  cancelled: "İptal edildi",
};

const exportJobTypeLabels = {
  preview: "Önizleme",
  final_export: "Final çıktı",
  regenerate_preview: "Önizlemeyi yenile",
  send_files: "Dosya gönderimi",
};

const PREVIEW_PAGE_WIDTH = 1240;
const PREVIEW_PAGE_HEIGHT = 1754;

function formatDateTime(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function mapFileForPanel(file) {
  const name = file.storage_key
    ? file.storage_key.split("/").pop()
    : file.url || `${file.file_type || "dosya"}-${String(file.id || "").slice(0, 8)}`;
  return {
    id: file.id,
    name,
    downloadName: name,
    type: file.file_type || "Kampanya dosyası",
    format: file.format || "-",
    size: file.size_bytes ? `${Math.round(file.size_bytes / 1024)} KB` : "-",
    status: fileStatusLabels[file.status] || file.status || "Bekliyor",
    rawStatus: file.status,
    createdAt: formatDateTime(file.created_at),
  };
}

function emptyCampaign(campaignId) {
  return {
    id: campaignId,
    name: "Kampanya yükleniyor",
    title: "Kampanya yükleniyor",
    market: "Demo Market",
    template: "Şablon yok",
    templateId: "",
    channel: "Panel",
    sourceType: "-",
    status: "Taslak",
    productCount: 0,
    matchedCount: 0,
    missingCount: 0,
    lowConfidenceCount: 0,
    createdAt: "-",
    updatedAt: "-",
    updatedAtFull: "-",
    campaignStartDate: "",
    campaignEndDate: "",
    files: [],
    exportJobs: [],
  };
}

function CampaignEditModal({ campaign, isSaving, error, onClose, onSave }) {
  const [form, setForm] = useState(() => ({
    title: campaign.title || campaign.name || "",
    templateId: campaign.templateId || "",
    campaignStartDate: campaign.campaignStartDate || "",
    campaignEndDate: campaign.campaignEndDate || "",
  }));

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function submit(event) {
    event.preventDefault();
    onSave(form);
  }

  return (
    <Modal
      title="Kampanyayı Düzenle"
      description="Kampanya başlığı, tarihleri ve şablon bilgisini güncelleyin."
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Vazgeç</Button>
          <Button variant="primary" type="submit" form="campaign-edit-form" disabled={isSaving}>
            {isSaving ? "Kaydediliyor..." : "Kaydet"}
          </Button>
        </>
      }
    >
      <form id="campaign-edit-form" className="form-grid" onSubmit={submit}>
        <label className="field field-full">
          <span>Başlık</span>
          <input value={form.title} onChange={(event) => update("title", event.target.value)} required />
        </label>
        <label className="field">
          <span>Başlangıç tarihi</span>
          <input type="date" value={form.campaignStartDate || ""} onChange={(event) => update("campaignStartDate", event.target.value)} />
        </label>
        <label className="field">
          <span>Bitiş tarihi</span>
          <input type="date" value={form.campaignEndDate || ""} onChange={(event) => update("campaignEndDate", event.target.value)} />
        </label>
        <label className="field">
          <span>Şablon ID</span>
          <input value={form.templateId || ""} onChange={(event) => update("templateId", event.target.value)} placeholder="Boş bırakılabilir" />
        </label>
        {error ? <p className="form-error field-full">{error}</p> : null}
      </form>
    </Modal>
  );
}

export function CampaignDetail({ campaignId, view = "" }) {
  const mockCampaign = findCampaignById(campaignId);
  const [campaign, setCampaign] = useState(() => (isRealApiEnabled ? emptyCampaign(campaignId) : mockCampaign));
  const [rows, setRows] = useState(() => (isRealApiEnabled ? [] : campaignProducts));
  const [selectedMissing, setSelectedMissing] = useState(null);
  const [confirmRemoveProduct, setConfirmRemoveProduct] = useState(null);
  const [notice, setNotice] = useState("");
  const [apiError, setApiError] = useState("");
  const [isLoading, setIsLoading] = useState(isRealApiEnabled);
  const [actionLoading, setActionLoading] = useState("");
  const [preview, setPreview] = useState(null);
  const [previewError, setPreviewError] = useState("");
  const [isPreviewLoading, setIsPreviewLoading] = useState(isRealApiEnabled);
  const [previewFile, setPreviewFile] = useState(null);
  const [previewingFileId, setPreviewingFileId] = useState(null);
  const previewViewportRef = useRef(null);
  const previewSectionRef = useRef(null);
  const [fitScale, setFitScale] = useState(1);
  const [previewZoom, setPreviewZoom] = useState(1);
  const [previewMode, setPreviewMode] = useState("fit");
  const [isEditing, setEditing] = useState(false);
  const [editError, setEditError] = useState("");
  const [isSavingEdit, setSavingEdit] = useState(false);
  const selectedMarketId = getSelectedMarketId();
  const canEditCampaigns = canMutateCampaigns();
  const canMutateCurrentCampaign = canEditCampaigns && !campaign.frozenAt;
  const canGenerateExports = canCreateExports();

  const measurePreview = useCallback(() => {
    const element = previewViewportRef.current;
    if (!element) return;
    const styles = getComputedStyle(element);
    const availableWidth = element.clientWidth - (parseFloat(styles.paddingLeft) || 0) - (parseFloat(styles.paddingRight) || 0);
    const availableHeight = element.clientHeight - (parseFloat(styles.paddingTop) || 0) - (parseFloat(styles.paddingBottom) || 0);
    if (availableWidth <= 0 || availableHeight <= 0) return;
    setFitScale(Math.min(availableWidth / PREVIEW_PAGE_WIDTH, availableHeight / PREVIEW_PAGE_HEIGHT));
  }, []);

  async function loadCampaign() {
    if (!isRealApiEnabled) return;

    try {
      setIsLoading(true);
      setCampaign(emptyCampaign(campaignId));
      setRows([]);
      const detail = await getCampaignDetail(campaignId);
      setCampaign(detail);
      setRows(detail.items || []);
      setApiError("");
    } catch (error) {
      setCampaign(emptyCampaign(campaignId));
      setRows([]);
      setApiError(error.message || "Kampanya detayı yüklenemedi.");
    } finally {
      setIsLoading(false);
    }
  }

  async function loadPreview() {
    if (!isRealApiEnabled) return;

    try {
      setIsPreviewLoading(true);
      setPreview(null);
      const previewResponse = await getCampaignPreviewHtml(campaignId);
      setPreview(previewResponse);
      setPreviewError("");
    } catch (error) {
      setPreview(null);
      setPreviewError(error.message || "Önizleme yüklenemedi. Placeholder gösteriliyor.");
    } finally {
      setIsPreviewLoading(false);
    }
  }

  useEffect(() => {
    loadCampaign();
    loadPreview();
  }, [campaignId, selectedMarketId]);

  useEffect(() => {
    if (view !== "preview" || isLoading) return;
    const node = previewSectionRef.current;
    if (!node) return;
    node.scrollIntoView({ behavior: "smooth", block: "start" });
    node.focus({ preventScroll: true });
  }, [view, isLoading]);

  useEffect(() => {
    const element = previewViewportRef.current;
    if (!element) return undefined;
    measurePreview();
    const observer = new ResizeObserver(measurePreview);
    observer.observe(element);
    window.addEventListener("resize", measurePreview);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measurePreview);
    };
  }, [preview?.html, measurePreview]);

  function restoreFit() {
    setPreviewMode("fit");
    setPreviewZoom(1);
    requestAnimationFrame(measurePreview);
  }

  function changeZoom(delta) {
    setPreviewMode("manual");
    setPreviewZoom((value) => Math.min(2, Math.max(0.5, Number((value + delta).toFixed(2)))));
  }

  async function runRealAction(key, action, successMessage) {
    try {
      setActionLoading(key);
      setApiError("");
      await action();
      await loadCampaign();
      setNotice(successMessage);
    } catch (error) {
      setApiError(error.message || "İşlem tamamlanamadı.");
    } finally {
      setActionLoading("");
    }
  }

  async function resolveProduct(status, suggestion) {
    if (!isRealApiEnabled) {
      setRows((currentRows) =>
        currentRows.map((row) => (row.id === selectedMissing?.id ? { ...row, status, score: Math.max(row.score, 82) } : row)),
      );
      setSelectedMissing(null);
      setNotice("Eksik ürün eşleştirmesi yerel olarak güncellendi.");
      return;
    }

    const item = selectedMissing;
    if (!item) return;
    setSelectedMissing(null);
    await runRealAction(
      `resolve-${item.id}`,
      () => resolveCampaignItem(campaignId, item, status, suggestion),
      "Ürün eşleştirmesi güncellendi.",
    );
  }

  async function generateFiles(formats) {
    await runRealAction(
      "export-job",
      () => createCampaignExportJob(campaignId, formats),
      formats?.length === 1 ? `${formats[0].toUpperCase()} dosyası üretildi.` : "PDF ve PNG dosyaları üretildi.",
    );
  }

  async function finalizeCurrentCampaign() {
    await runRealAction("finalize", () => finalizeCampaign(campaignId), "Kampanya donduruldu ve sürümü sabitlendi.");
  }

  async function moveRow(index, direction) {
    if (!isRealApiEnabled || campaign.frozenAt || index + direction < 0 || index + direction >= rows.length) return;
    const next = [...rows];
    [next[index], next[index + direction]] = [next[index + direction], next[index]];
    setRows(next);
    try {
      const updated = await reorderCampaignItems(campaignId, next);
      setCampaign(updated);
      setRows(updated.items || next);
      setNotice("Ürün sırası kaydedildi.");
    } catch (error) {
      setApiError(error.message || "Ürün sırası kaydedilemedi.");
      await loadCampaign();
    }
  }

  async function downloadFile(file) {
    if (!isRealApiEnabled) {
      setNotice("Mock modda indirme simüle edildi.");
      return;
    }
    try {
      setActionLoading(`download-${file.id}`);
      setApiError("");
      await downloadCampaignFile(campaignId, file);
      setNotice("Dosya indirildi.");
    } catch (error) {
      setApiError(error.message || "Dosya indirilemedi.");
    } finally {
      setActionLoading("");
    }
  }

  async function previewFileContent(file) {
    if (!isRealApiEnabled || !file?.id || file.rawStatus !== "ready" || previewingFileId) return;
    try {
      setPreviewingFileId(file.id);
      setApiError("");
      const blob = await fetchCampaignFile(campaignId, file.id, selectedMarketId);
      const url = URL.createObjectURL(blob);
      setPreviewFile({ id: file.id, url, type: blob.type || (String(file.format).toLowerCase() === "pdf" ? "application/pdf" : "image/png"), name: file.name });
    } catch (error) {
      setApiError(error.message || "Önizleme yüklenemedi.");
    } finally {
      setPreviewingFileId(null);
    }
  }

  useEffect(() => () => {
    if (previewFile?.url) URL.revokeObjectURL(previewFile.url);
  }, [previewFile]);

  async function saveCampaignEdit(form) {
    try {
      setSavingEdit(true);
      setEditError("");
      const updated = await updateCampaignDetail(campaignId, form);
      setCampaign(updated);
      setRows(updated.items || []);
      setEditing(false);
      setNotice("Kampanya güncellendi.");
    } catch (error) {
      setEditError(error.message || "Kampanya güncellenemedi.");
    } finally {
      setSavingEdit(false);
    }
  }

  function removeMockCampaignItem(product) {
    if (!product) return;
    setRows((currentRows) => currentRows.filter((row) => row.id !== product.id));
    setConfirmRemoveProduct(null);
    setNotice("Ürün kampanyadan çıkarıldı.");
  }

  async function analyzeIntelligence() {
    await runRealAction(
      "campaign-intelligence-analyze",
      () => analyzeCampaignIntelligence(campaignId),
      "Kampanya analizi g\u00fcncellendi.",
    );
  }

  async function applyIntelligence() {
    await runRealAction(
      "campaign-intelligence-apply",
      () => applyCampaignIntelligence(campaignId),
      "Kampanya plan\u0131 \u00f6nizleme ve \u00e7\u0131kt\u0131lara uyguland\u0131.",
    );
    await loadPreview();
  }

  const intelligence = campaign.intelligence;
  const intelligenceProducts = intelligence?.products || [];
  const heroRecommendation = intelligenceProducts.find((product) => product.role === "hero");
  const productName = (productId) =>
    rows.find((row) => row.id === productId)?.matchedProduct
    || rows.find((row) => row.id === productId)?.incomingName
    || "\u00dcr\u00fcn";
  const intelligenceBadgeLabel = (product) => {
    if (product.recommendedBadge === "save_percent" && product.discountPercent) {
      return `\u00d6nerilen rozet: %${product.discountPercent} indirim`;
    }
    if (product.recommendedBadge === "save_amount" && product.absoluteSaving) {
      return `\u00d6nerilen rozet: ${product.absoluteSaving} tasarruf`;
    }
    if (product.recommendedBadge === "special") return "\u00d6nerilen rozet: \u00d6zel teklif";
    if (product.recommendedBadge === "best_value") return "\u00d6nerilen rozet: Avantajl\u0131";
    return "";
  };
  const missingRows = rows.filter((row) => needsAttention(row.status));
  const files = isRealApiEnabled ? (campaign.files || []).map(mapFileForPanel) : generatedFiles;
  const exportJobs = campaign.exportJobs || [];

  return (
    <>
      <PageHeader
        title={campaign.name}
        description={`${campaign.market} · ${campaign.template} · ${campaign.channel} · ${campaign.createdAt}`}
        actions={
          <>
            {canEditCampaigns ? (
              <>
                <Button href={campaign.frozenAt ? `#/campaigns/new?source=${campaignId}` : `#/campaigns/${campaignId}/edit`} disabled={isLoading}>
                  {campaign.frozenAt ? "Yeni Revizyon Oluştur" : "Broşürü Düzenle"}
                </Button>
                {canMutateCurrentCampaign ? <Button
                  disabled={isLoading || actionLoading === "all-suggestions"}
                  onClick={() =>
                    isRealApiEnabled
                      ? runRealAction(
                          "all-suggestions",
                          () => generateCampaignDetailSuggestions(campaignId),
                          "Tüm ürünler için öneriler güncellendi.",
                        )
                      : setNotice("Öneri üretimi mock modda simüle edildi.")
                  }
                >
                  {actionLoading === "all-suggestions" ? "Öneriler üretiliyor..." : "Tüm Önerileri Üret"}
                </Button> : null}
              </>
            ) : null}
            {canMutateCurrentCampaign && isRealApiEnabled ? (
              <Button variant="primary" disabled={isLoading || actionLoading === "finalize"} onClick={finalizeCurrentCampaign}>
                {actionLoading === "finalize" ? "Donduruluyor..." : "Kampanyayı Dondur"}
              </Button>
            ) : null}
            {canGenerateExports ? (
              <Button
                disabled={isLoading || actionLoading === "export-job"}
                onClick={() =>
                  isRealApiEnabled
                    ? runRealAction(
                        "export-job",
                        () => createCampaignExportJob(campaignId, ["pdf", "png"]),
                        "PDF ve PNG dosyaları üretildi.",
                      )
                    : setNotice("Final dosyaları üretim için hazırlandı.")
                }
              >
                {actionLoading === "export-job" ? "Dosya üretiliyor..." : "Dosya Üret"}
              </Button>
            ) : null}
          </>
        }
      />
      {notice ? <p className="inline-result">{notice}</p> : null}
      {apiError ? <p className="inline-result inline-result-warning">{apiError}</p> : null}
      {isLoading ? <p className="inline-result">Kampanya detayı yükleniyor...</p> : null}

      <section className="detail-hero card">
        <div>
          <StatusBadge status={campaign.status} />
          <h2>{campaign.name}</h2>
          <p>Market, kaynak, kanal ve ürün eşleşme durumu bu kampanya üzerinden takip ediliyor.</p>
        </div>
        <dl className="summary-grid">
          <div><dt>Market</dt><dd>{campaign.market}</dd></div>
          <div><dt>Kaynak</dt><dd>{campaign.sourceType || campaign.template}</dd></div>
          <div><dt>Kanal</dt><dd>{campaign.channel}</dd></div>
          <div><dt>Ürün</dt><dd>{campaign.productCount}</dd></div>
          <div><dt>Eşleşen</dt><dd>{campaign.matchedCount ?? "-"}</dd></div>
          <div><dt>Eksik</dt><dd>{campaign.missingCount ?? "-"}</dd></div>
          <div><dt>Düşük Güven</dt><dd>{campaign.lowConfidenceCount ?? "-"}</dd></div>
          <div><dt>Güncelleme</dt><dd>{campaign.updatedAtFull || campaign.updatedAt}</dd></div>
        </dl>
      </section>

      <section className="dashboard-grid">
        <Card title={"Kampanya Zek\u00e2s\u0131"} className="span-12">
          <div className="intelligence-panel">
            <div className="intelligence-toolbar">
              <div>
                <strong>{intelligence ? "Yap\u0131land\u0131r\u0131lm\u0131\u015f kampanya plan\u0131 haz\u0131r" : "Kampanyan\u0131z\u0131 analiz ederek \u00fcr\u00fcn \u00f6nceliklerini belirleyin"}</strong>
                <small>{campaign.intelligenceAnalyzedAt ? `Son analiz: ${formatDateTime(campaign.intelligenceAnalyzedAt)} - ${intelligence?.engineVersion}` : "Analiz kampanya verileriyle \u00e7evrimd\u0131\u015f\u0131 ve deterministik \u00e7al\u0131\u015f\u0131r."}</small>
              </div>
              {canMutateCurrentCampaign ? <div className="page-actions">
                <Button disabled={Boolean(campaign.frozenAt) || actionLoading === "campaign-intelligence-analyze"} onClick={analyzeIntelligence}>
                  {actionLoading === "campaign-intelligence-analyze" ? "Analiz ediliyor..." : intelligence ? "Yeniden Analiz Et" : "Kampanyay\u0131 Analiz Et"}
                </Button>
                <Button variant="primary" disabled={!intelligence || Boolean(campaign.frozenAt) || actionLoading === "campaign-intelligence-apply"} onClick={applyIntelligence}>
                  {actionLoading === "campaign-intelligence-apply" ? "Uygulan\u0131yor..." : campaign.intelligenceApplied ? "Plan Uyguland\u0131" : "Plan\u0131 Uygula"}
                </Button>
              </div> : null}
            </div>
            {intelligence ? <>
              <dl className="summary-grid intelligence-summary">
                <div><dt>Kompozisyon</dt><dd>{({ hero_plus_grid: "Hero + \u00fcr\u00fcn \u0131zgaras\u0131", balanced_grid: "Dengeli \u00fcr\u00fcn \u0131zgaras\u0131", dense_value_grid: "Yo\u011fun f\u0131rsat \u0131zgaras\u0131" })[intelligence.strategy.composition] || intelligence.strategy.composition}</dd></div>
                <div><dt>{"Yo\u011funluk"}</dt><dd>{intelligence.strategy.density === "dense" ? "Yo\u011fun" : "Dengeli"}</dd></div>
                <div><dt>Odak</dt><dd>{intelligence.strategy.campaignType === "discount_led" ? "\u0130ndirim" : intelligence.strategy.campaignType === "price_led" ? "Fiyat" : "\u00dcr\u00fcn g\u00f6rseli"}</dd></div>
                <div><dt>{"Hero \u00fcr\u00fcn"}</dt><dd>{heroRecommendation ? productName(heroRecommendation.productId) : "\u00d6neri yok"}</dd></div>
              </dl>
                <div><dt>Gruplar</dt><dd>{(intelligence.groups || []).map((group) => `${group.key} (${group.productCount})`).join(", ") || "-"}</dd></div>
              <div className="intelligence-products">
                {intelligenceProducts.slice(0, 6).map((product) => <article key={product.productId}>
                  <div><strong>{productName(product.productId)}</strong><small>{[...product.reasons.slice(0, 3), intelligenceBadgeLabel(product)].filter(Boolean).join(" - ")}</small></div>
                  <Badge tone={product.role === "hero" ? "success" : "neutral"}>{product.role === "hero" ? "Hero" : product.role === "featured" ? "\u00d6ne \u00e7\u0131kan" : "Standart"} - {product.priorityScore}</Badge>
                </article>)}
              </div>
              {(intelligence.warnings || []).length ? <div className="intelligence-warnings"><strong>Kontrol edilmesi gerekenler</strong>{intelligence.warnings.map((warning) => <p key={warning}>{warning}</p>)}</div> : null}
            </> : <p className="catalog-empty">{"Hen\u00fcz bir analiz yok. \u00d6neriler kampanyay\u0131 siz onaylayana kadar \u00fcr\u00fcnleri veya \u00f6nizlemeyi de\u011fi\u015ftirmez."}</p>}
          </div>
        </Card>

        <div
          id="campaign-preview-section"
          ref={previewSectionRef}
          tabIndex={-1}
          className="span-8 campaign-preview-section"
        >
          <Card title="Broşür Önizleme">
          {isRealApiEnabled ? (
            <div className="real-preview-panel">
              <div className="real-preview-toolbar">
                <div>
                  <strong>{preview?.template_name || campaign.template}</strong>
                  <small>{preview?.generated_at ? `Son üretim: ${formatDateTime(preview.generated_at)}` : "HTML önizleme"}</small>
                </div>
                <Button disabled={isPreviewLoading} onClick={loadPreview}>
                  {isPreviewLoading ? "Önizleme yükleniyor..." : "Önizlemeyi Yenile"}
                </Button>
              </div>
              {previewError ? <p className="inline-result inline-result-warning">{previewError}</p> : null}
              {preview?.html ? (
                <>
                  <div className="preview-control-actions" aria-label="Önizleme yakınlaştırma kontrolleri">
                    <Button onClick={restoreFit}>Sayfaya sığdır</Button>
                    <Button disabled={previewZoom <= 0.5} onClick={() => changeZoom(-0.1)}>−</Button>
                    <span className="preview-zoom-label">{Math.round(fitScale * previewZoom * 100)}%</span>
                    <Button disabled={previewZoom >= 2} onClick={() => changeZoom(0.1)}>+</Button>
                    <Button onClick={restoreFit}>Sıfırla</Button>
                  </div>
                  <div ref={previewViewportRef} className={`campaign-preview-viewport ${previewMode === "manual" ? "is-zoomed" : "is-fit"}`}>
                    <div className="campaign-preview-page-box" style={{ width: PREVIEW_PAGE_WIDTH * fitScale * previewZoom, height: PREVIEW_PAGE_HEIGHT * fitScale * previewZoom }}>
                      <iframe className="campaign-preview-iframe" style={{ transform: `scale(${fitScale * previewZoom})` }} sandbox="" srcDoc={preview.html} title={`${campaign.name} önizleme`} />
                    </div>
                  </div>
                </>
              ) : (
                <PreviewFrame title={campaign.name} status="Placeholder önizleme" />
              )}
            </div>
          ) : (
            <PreviewFrame title={campaign.name} status="Placeholder önizleme" />
          )}
        </Card>
        </div>

        <Card title="Eksik Ürünler" className="span-4">
          <div className="stack-list">
            {missingRows.length === 0 ? <p className="catalog-empty">Kontrol gerektiren ürün yok.</p> : null}
            {missingRows.map((product) => (
              <article className="missing-action-row" key={product.id}>
                <div>
                  <strong>{product.incomingName}</strong>
                  <small>{product.matchedProduct}</small>
                </div>
                <StatusBadge status={product.status} />
                {canMutateCurrentCampaign ? (
                  <div className="row-actions">
                    <Button onClick={() => setSelectedMissing(product)}>Eşleştir</Button>
                    {isRealApiEnabled ? (
                      <Button
                        disabled={actionLoading === `item-suggestions-${product.id}`}
                        onClick={() =>
                          runRealAction(
                            `item-suggestions-${product.id}`,
                            () => generateCampaignItemSuggestions(campaignId, product.id),
                            "Ürün önerileri güncellendi.",
                          )
                        }
                      >
                        Öneri Üret
                      </Button>
                    ) : (
                      <Button onClick={() => setConfirmRemoveProduct(product)}>Kampanyadan çıkar</Button>
                    )}
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        </Card>

        <Card title="Ürün Eşleştirme Tablosu" className="span-12">
          <Table
            columns={[
              "Görsel",
              "Gelen Ürün Adı",
              "Eşleşen Ürün",
              "Fiyat",
              "Eski Fiyat",
              "Kategori",
              "Eşleşme Skoru",
              "Durum",
              canMutateCurrentCampaign ? "Sıra" : null,
              canMutateCurrentCampaign ? "Öneriler" : null,
              canMutateCurrentCampaign ? "Aksiyon" : null,
            ].filter(Boolean)}
          >
            {rows.map((product, index) => (
              <tr key={product.id}>
                <td><ProductThumbnail label={product.matchedProduct || product.incomingName} hasImage={product.image} /></td>
                <td>{product.incomingName}{product.rawLine ? <small>{product.rawLine}</small> : null}</td>
                <td><strong>{product.matchedProduct}</strong></td>
                <td>{product.price}</td>
                <td>{product.oldPrice}</td>
                <td>{product.category}</td>
                <td><Badge tone={scoreTone(product.score)}>{product.score ? `%${product.score}` : "-"}</Badge></td>
                <td><StatusBadge status={product.status} /></td>
                {canMutateCurrentCampaign ? (
                  <>
                    <td>
                      <Button disabled={Boolean(campaign.frozenAt) || index === 0} onClick={() => moveRow(index, -1)}>↑</Button>
                      <Button disabled={Boolean(campaign.frozenAt) || index === rows.length - 1} onClick={() => moveRow(index, 1)}>↓</Button>
                    </td>
                    <td>
                      {(product.suggestions || []).slice(0, 2).map((suggestion) => (
                        <button
                          className="table-action"
                          type="button"
                          key={suggestion.id}
                          disabled={actionLoading === `resolve-${product.id}`}
                          onClick={() =>
                            runRealAction(
                              `resolve-${product.id}`,
                              () => resolveCampaignItem(campaignId, product, "Eşleşti", suggestion),
                              "Ürün eşleştirmesi güncellendi.",
                            )
                          }
                        >
                          {suggestion.suggested_name || "Öneri"} (%{Math.round(Number(suggestion.score || 0))})
                        </button>
                      ))}
                      {isRealApiEnabled && !(product.suggestions || []).length ? <small>Öneri yok</small> : null}
                    </td>
                    <td>
                      <button className="table-action" type="button" onClick={() => setSelectedMissing(product)}>
                        Eşleştir
                      </button>
                    </td>
                  </>
                ) : null}
              </tr>
            ))}
          </Table>
        </Card>

        <Card title="Çıktılar" className="span-12">
          <ExportPanel
            files={files}
            isGenerating={actionLoading === "export-job"}
            onDownload={isRealApiEnabled ? downloadFile : undefined}
            onPreview={isRealApiEnabled ? previewFileContent : undefined}
            previewingFileId={previewingFileId}
            onAction={canGenerateExports ? (message, formats) => (isRealApiEnabled ? generateFiles(formats) : setNotice(message)) : undefined}
          />
        </Card>

        {isRealApiEnabled ? (
          <Card title="Çıktı İşleri" className="span-12">
            {exportJobs.length === 0 ? <p className="catalog-empty">Henüz çıktı işi yok.</p> : null}
            {exportJobs.length ? (
              <Table columns={["Tip", "Durum", "Formatlar", "Deneme", "Oluşturma"]}>
                {exportJobs.map((job) => (
                  <tr key={job.id}>
                    <td>{exportJobTypeLabels[job.job_type] || job.job_type}</td>
                    <td><StatusBadge status={exportJobStatusLabels[job.status] || job.status || "Bekliyor"} /></td>
                    <td>{(job.requested_formats || []).join(", ") || "-"}</td>
                    <td>{job.attempts ?? 0}</td>
                    <td>{formatDateTime(job.created_at)}</td>
                  </tr>
                ))}
              </Table>
            ) : null}
          </Card>
        ) : null}
      </section>

      {canMutateCurrentCampaign ? <MissingProductModal product={selectedMissing} onClose={() => setSelectedMissing(null)} onResolve={resolveProduct} /> : null}
      {previewFile ? (
        <Modal title={`${previewFile.name} önizleme`} onClose={() => setPreviewFile(null)} className="file-preview-modal">
          {previewFile.type === "application/pdf" ? (
            <iframe className="file-preview-content" src={previewFile.url} title={`${previewFile.name} önizleme`} />
          ) : (
            <img className="file-preview-content" src={previewFile.url} alt={`${previewFile.name} önizleme`} />
          )}
        </Modal>
      ) : null}
      {canMutateCurrentCampaign && isEditing ? (
        <CampaignEditModal
          campaign={campaign}
          isSaving={isSavingEdit}
          error={editError}
          onClose={() => setEditing(false)}
          onSave={saveCampaignEdit}
        />
      ) : null}
      <ConfirmDialog
        isOpen={Boolean(confirmRemoveProduct)}
        title="Ürünü kampanyadan çıkar"
        description={
          confirmRemoveProduct
            ? `${confirmRemoveProduct.incomingName} kampanya ürün listesinden çıkarılacak. Devam edilsin mi?`
            : ""
        }
        confirmLabel="Kampanyadan çıkar"
        onCancel={() => setConfirmRemoveProduct(null)}
        onConfirm={() => removeMockCampaignItem(confirmRemoveProduct)}
      />
    </>
  );
}
