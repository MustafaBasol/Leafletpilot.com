import { useEffect, useState } from "react";
import { isRealApiEnabled } from "../api/config.js";
import {
  campaignActivities,
  campaignProducts,
  findCampaignById,
  generatedFiles,
  messages,
} from "../data/mockData.js";
import {
  createCampaignExportJob,
  downloadCampaignFile,
  generateCampaignDetailSuggestions,
  generateCampaignItemSuggestions,
  getCampaignDetail,
  getCampaignPreviewHtml,
  resolveCampaignItem,
} from "../data/dataSource.js";
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  ExportPanel,
  MissingProductModal,
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
  return ["Kontrol gerekli", "BulunamadÄ±", "Yeni Ã¼rÃ¼n gerekli", "GÃ¶rselsiz devam"].includes(status);
}

const fileStatusLabels = {
  pending: "Bekliyor",
  generating: "OluÅŸturuluyor",
  ready: "HazÄ±r",
  failed: "BaÅŸarÄ±sÄ±z",
  sent: "GÃ¶nderildi",
};

const exportJobStatusLabels = {
  queued: "Kuyrukta",
  running: "Ã‡alÄ±ÅŸÄ±yor",
  completed: "TamamlandÄ±",
  failed: "BaÅŸarÄ±sÄ±z",
  cancelled: "Ä°ptal edildi",
};

const exportJobTypeLabels = {
  preview: "Ã–nizleme",
  final_export: "Final Ã§Ä±ktÄ±",
  regenerate_preview: "Ã–nizlemeyi yenile",
  send_files: "Dosya gÃ¶nderimi",
};

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
    type: file.file_type || "Kampanya dosyasÄ±",
    format: file.format || "-",
    size: file.size_bytes ? `${Math.round(file.size_bytes / 1024)} KB` : "-",
    status: fileStatusLabels[file.status] || file.status || "Bekliyor",
    createdAt: formatDateTime(file.created_at),
  };
}

function emptyCampaign(campaignId) {
  return {
    id: campaignId,
    name: "Kampanya yÃ¼kleniyor",
    market: "Demo Market",
    template: "Åžablon yok",
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
    files: [],
    exportJobs: [],
  };
}

export function CampaignDetail({ campaignId }) {
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

  async function loadCampaign() {
    if (!isRealApiEnabled) return;

    try {
      setIsLoading(true);
      const detail = await getCampaignDetail(campaignId);
      setCampaign(detail);
      setRows(detail.items || []);
      setApiError("");
    } catch (error) {
      setApiError(error.message || "Kampanya detayÄ± yÃ¼klenemedi.");
    } finally {
      setIsLoading(false);
    }
  }

  async function loadPreview() {
    if (!isRealApiEnabled) return;

    try {
      setIsPreviewLoading(true);
      const previewResponse = await getCampaignPreviewHtml(campaignId);
      setPreview(previewResponse);
      setPreviewError("");
    } catch (error) {
      setPreview(null);
      setPreviewError(error.message || "Ã–nizleme yÃ¼klenemedi. Placeholder gÃ¶steriliyor.");
    } finally {
      setIsPreviewLoading(false);
    }
  }

  useEffect(() => {
    loadCampaign();
    loadPreview();
  }, [campaignId]);

  async function runRealAction(key, action, successMessage) {
    try {
      setActionLoading(key);
      setApiError("");
      await action();
      await loadCampaign();
      setNotice(successMessage);
    } catch (error) {
      setApiError(error.message || "Ä°ÅŸlem tamamlanamadÄ±.");
    } finally {
      setActionLoading("");
    }
  }

  function resolveMockProduct(status) {
    setRows((currentRows) =>
      currentRows.map((row) => (row.id === selectedMissing?.id ? { ...row, status, score: Math.max(row.score, 82) } : row)),
    );
    setSelectedMissing(null);
    setNotice("Eksik Ã¼rÃ¼n eÅŸleÅŸtirmesi yerel olarak gÃ¼ncellendi.");
  }

  async function resolveProduct(status, suggestion) {
    if (!isRealApiEnabled) {
      resolveMockProduct(status);
      return;
    }

    const item = selectedMissing;
    if (!item) return;
    if (status === "EÅŸleÅŸti" && !suggestion?.product_id && !item.productId) {
      setApiError("Real API modunda eÅŸleÅŸtirme iÃ§in backend Ã¶nerisinden Ã¼rÃ¼n seÃ§in.");
      return;
    }
    setSelectedMissing(null);
    await runRealAction(
      `resolve-${item.id}`,
      () => resolveCampaignItem(campaignId, item, status, suggestion),
      "ÃœrÃ¼n eÅŸleÅŸtirmesi gÃ¼ncellendi.",
    );
  }

  function removeMockCampaignItem(product) {
    if (!product) return;
    setRows((currentRows) => currentRows.filter((row) => row.id !== product.id));
    setConfirmRemoveProduct(null);
    setNotice("ÃœrÃ¼n kampanyadan Ã§Ä±karÄ±ldÄ±.");
  }

  async function generateFiles(formats) {
    await runRealAction(
      "export-job",
      () => createCampaignExportJob(campaignId, formats),
      formats?.length === 1 ? `${formats[0].toUpperCase()} dosyasÄ± Ã¼retildi.` : "PDF ve PNG dosyalarÄ± Ã¼retildi.",
    );
  }

  async function downloadFile(file) {
    if (!isRealApiEnabled) {
      setNotice("Mock modda indirme simÃ¼le edildi.");
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

  const missingRows = rows.filter((row) => needsAttention(row.status));
  const files = isRealApiEnabled ? (campaign.files || []).map(mapFileForPanel) : generatedFiles;
  const exportJobs = campaign.exportJobs || [];

  return (
    <>
      <PageHeader
        title={campaign.name}
        description={`${campaign.market} Â· ${campaign.template} Â· ${campaign.channel} Â· ${campaign.createdAt}`}
        actions={
          <>
            <Button
              disabled={isLoading || actionLoading === "all-suggestions"}
              onClick={() =>
                isRealApiEnabled
                  ? runRealAction(
                      "all-suggestions",
                      () => generateCampaignDetailSuggestions(campaignId),
                      "TÃ¼m Ã¼rÃ¼nler iÃ§in Ã¶neriler gÃ¼ncellendi.",
                    )
                  : setNotice("Ã–neri Ã¼retimi mock modda simÃ¼le edildi.")
              }
            >
              {actionLoading === "all-suggestions" ? "Ã–neriler Ã¼retiliyor..." : "TÃ¼m Ã–nerileri Ãœret"}
            </Button>
            <Button
              disabled={isLoading || actionLoading === "export-job"}
              onClick={() =>
                isRealApiEnabled
                  ? runRealAction(
                      "export-job",
                      () => createCampaignExportJob(campaignId, ["pdf", "png"]),
                      "PDF ve PNG dosyalarÄ± Ã¼retildi.",
                    )
                  : setNotice("Final dosyalarÄ± Ã¼retim iÃ§in hazÄ±rlandÄ±.")
              }
            >
              {actionLoading === "export-job" ? "Dosya Ã¼retiliyor..." : "Dosya Ãœret"}
            </Button>
            <Button variant="primary" onClick={() => setNotice("Dosya gÃ¶nderimi bu fazda placeholder olarak kalÄ±yor.")}>
              KullanÄ±cÄ±ya GÃ¶nder
            </Button>
          </>
        }
      />
      {notice ? <p className="inline-result">{notice}</p> : null}
      {apiError ? <p className="inline-result inline-result-warning">{apiError}</p> : null}
      {isLoading ? <p className="inline-result">Kampanya detayÄ± yÃ¼kleniyor...</p> : null}

      <section className="detail-hero card">
        <div>
          <StatusBadge status={campaign.status} />
          <h2>{campaign.name}</h2>
          <p>Market, kaynak, kanal ve Ã¼rÃ¼n eÅŸleÅŸme durumu bu kampanya Ã¼zerinden takip ediliyor.</p>
        </div>
        <dl className="summary-grid">
          <div>
            <dt>Market</dt>
            <dd>{campaign.market}</dd>
          </div>
          <div>
            <dt>Kaynak</dt>
            <dd>{campaign.sourceType || campaign.template}</dd>
          </div>
          <div>
            <dt>Kanal</dt>
            <dd>{campaign.channel}</dd>
          </div>
          <div>
            <dt>ÃœrÃ¼n</dt>
            <dd>{campaign.productCount}</dd>
          </div>
          <div>
            <dt>EÅŸleÅŸen</dt>
            <dd>{campaign.matchedCount ?? "-"}</dd>
          </div>
          <div>
            <dt>Eksik</dt>
            <dd>{campaign.missingCount ?? "-"}</dd>
          </div>
          <div>
            <dt>DÃ¼ÅŸÃ¼k GÃ¼ven</dt>
            <dd>{campaign.lowConfidenceCount ?? "-"}</dd>
          </div>
          <div>
            <dt>GÃ¼ncelleme</dt>
            <dd>{campaign.updatedAtFull || campaign.updatedAt}</dd>
          </div>
        </dl>
      </section>

      <section className="dashboard-grid">
        <Card title="BroÅŸÃ¼r Ã–nizleme" className="span-8">
          {isRealApiEnabled ? (
            <div className="real-preview-panel">
              <div className="real-preview-toolbar">
                <div>
                  <strong>{preview?.template_name || campaign.template}</strong>
                  <small>{preview?.generated_at ? `Son Ã¼retim: ${formatDateTime(preview.generated_at)}` : "HTML Ã¶nizleme"}</small>
                </div>
                <Button disabled={isPreviewLoading} onClick={loadPreview}>
                  {isPreviewLoading ? "Ã–nizleme yÃ¼kleniyor..." : "Ã–nizlemeyi Yenile"}
                </Button>
              </div>
              {previewError ? <p className="inline-result inline-result-warning">{previewError}</p> : null}
              {preview?.html ? (
                <iframe
                  className="campaign-preview-iframe"
                  sandbox=""
                  srcDoc={preview.html}
                  title={`${campaign.name} Ã¶nizleme`}
                />
              ) : (
                <PreviewFrame title={campaign.name} status="Placeholder Ã¶nizleme" />
              )}
            </div>
          ) : (
            <PreviewFrame title={campaign.name} status="Placeholder Ã¶nizleme" />
          )}
        </Card>

        <Card title="Eksik ÃœrÃ¼nler" className="span-4">
          <div className="stack-list">
            {missingRows.length === 0 ? <p className="catalog-empty">Kontrol gerektiren Ã¼rÃ¼n yok.</p> : null}
            {missingRows.map((product) => (
              <article className="missing-action-row" key={product.id}>
                <div>
                  <strong>{product.incomingName}</strong>
                  <small>{product.matchedProduct}</small>
                </div>
                <StatusBadge status={product.status} />
                <div className="row-actions">
                  <Button onClick={() => setSelectedMissing(product)}>EÅŸleÅŸtir</Button>
                  {isRealApiEnabled ? (
                    <Button
                      disabled={actionLoading === `item-suggestions-${product.id}`}
                      onClick={() =>
                        runRealAction(
                          `item-suggestions-${product.id}`,
                          () => generateCampaignItemSuggestions(campaignId, product.id),
                          "ÃœrÃ¼n Ã¶nerileri gÃ¼ncellendi.",
                        )
                      }
                    >
                      Ã–neri Ãœret
                    </Button>
                  ) : (
                    <Button onClick={() => setConfirmRemoveProduct(product)}>Kampanyadan çıkar</Button>
                  )}
                </div>
              </article>
            ))}
          </div>
        </Card>

        <Card title="ÃœrÃ¼n EÅŸleÅŸtirme Tablosu" className="span-12">
          <Table
            columns={[
              "GÃ¶rsel",
              "Gelen ÃœrÃ¼n AdÄ±",
              "EÅŸleÅŸen ÃœrÃ¼n",
              "Fiyat",
              "Eski Fiyat",
              "Kategori",
              "EÅŸleÅŸme Skoru",
              "Durum",
              "Ã–neriler",
              "Aksiyon",
            ]}
          >
            {rows.map((product) => (
              <tr key={product.id}>
                <td>
                  <ProductThumbnail label={product.matchedProduct || product.incomingName} hasImage={product.image} />
                </td>
                <td>
                  {product.incomingName}
                  {product.rawLine ? <small>{product.rawLine}</small> : null}
                </td>
                <td>
                  <strong>{product.matchedProduct}</strong>
                </td>
                <td>{product.price}</td>
                <td>{product.oldPrice}</td>
                <td>{product.category}</td>
                <td>
                  <Badge tone={scoreTone(product.score)}>{product.score ? `%${product.score}` : "-"}</Badge>
                </td>
                <td>
                  <StatusBadge status={product.status} />
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
                          () => resolveCampaignItem(campaignId, product, "EÅŸleÅŸti", suggestion),
                          "ÃœrÃ¼n eÅŸleÅŸtirmesi gÃ¼ncellendi.",
                        )
                      }
                    >
                      {suggestion.suggested_name || "Ã–neri"} (%{Math.round(Number(suggestion.score || 0))})
                    </button>
                  ))}
                  {isRealApiEnabled && !(product.suggestions || []).length ? <small>Ã–neri yok</small> : null}
                </td>
                <td>
                  <button className="table-action" type="button" onClick={() => setSelectedMissing(product)}>
                    EÅŸleÅŸtir
                  </button>
                </td>
              </tr>
            ))}
          </Table>
        </Card>

        <Card title="Ã‡Ä±ktÄ±lar" className="span-12">
          <ExportPanel
            files={files}
            isGenerating={actionLoading === "export-job"}
            onDownload={isRealApiEnabled ? downloadFile : undefined}
            onAction={(message, formats) =>
              isRealApiEnabled
                ? generateFiles(formats)
                : setNotice(message)
            }
          />
        </Card>

        {isRealApiEnabled ? (
          <Card title="Ã‡Ä±ktÄ± Ä°ÅŸleri" className="span-12">
            {exportJobs.length === 0 ? <p className="catalog-empty">HenÃ¼z Ã§Ä±ktÄ± iÅŸi yok.</p> : null}
            {exportJobs.length ? (
              <Table columns={["Tip", "Durum", "Formatlar", "Deneme", "OluÅŸturma"]}>
                {exportJobs.map((job) => (
                  <tr key={job.id}>
                    <td>{exportJobTypeLabels[job.job_type] || job.job_type}</td>
                    <td>
                      <StatusBadge status={exportJobStatusLabels[job.status] || job.status || "Bekliyor"} />
                    </td>
                    <td>{(job.requested_formats || []).join(", ") || "-"}</td>
                    <td>{job.attempts ?? 0}</td>
                    <td>{formatDateTime(job.created_at)}</td>
                  </tr>
                ))}
              </Table>
            ) : null}
          </Card>
        ) : null}

        <Card title="Mesaj GeÃ§miÅŸi" className="span-6">
          <div className="message-list">
            {messages.map((message) => (
              <article key={`${message.sender}-${message.time}`}>
                <strong>{message.sender}</strong>
                <p>{message.text}</p>
                <small>{message.time}</small>
              </article>
            ))}
          </div>
        </Card>

        <Card title="Ä°ÅŸlem GeÃ§miÅŸi" className="span-6">
          <ol className="activity-timeline">
            {campaignActivities.map((activity) => (
              <li key={activity.label}>
                <Badge tone={activity.tone}>{activity.time}</Badge>
                <span>{activity.label}</span>
              </li>
            ))}
          </ol>
        </Card>
      </section>

      <MissingProductModal product={selectedMissing} onClose={() => setSelectedMissing(null)} onResolve={resolveProduct} />
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
