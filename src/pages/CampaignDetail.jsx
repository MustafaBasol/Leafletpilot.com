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
  generateCampaignDetailSuggestions,
  generateCampaignItemSuggestions,
  getCampaignDetail,
  resolveCampaignItem,
} from "../data/dataSource.js";
import {
  Badge,
  Button,
  Card,
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
  return ["Kontrol gerekli", "Bulunamadı", "Yeni ürün gerekli", "Görselsiz devam"].includes(status);
}

function mapFileForPanel(file) {
  return {
    name: file.storage_key || file.url || `${file.file_type || "dosya"}-${String(file.id || "").slice(0, 8)}`,
    type: file.file_type || "Kampanya dosyası",
    format: file.format || "-",
    size: file.size_bytes ? `${Math.round(file.size_bytes / 1024)} KB` : "-",
    status: file.status || "Bekliyor",
    createdAt: file.created_at || "",
  };
}

function emptyCampaign(campaignId) {
  return {
    id: campaignId,
    name: "Kampanya yükleniyor",
    market: "Demo Market",
    template: "Şablon yok",
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
  const [notice, setNotice] = useState("");
  const [apiError, setApiError] = useState("");
  const [isLoading, setIsLoading] = useState(isRealApiEnabled);
  const [actionLoading, setActionLoading] = useState("");

  async function loadCampaign() {
    if (!isRealApiEnabled) return;

    try {
      setIsLoading(true);
      const detail = await getCampaignDetail(campaignId);
      setCampaign(detail);
      setRows(detail.items || []);
      setApiError("");
    } catch (error) {
      setApiError(error.message || "Kampanya detayı yüklenemedi.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadCampaign();
  }, [campaignId]);

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

  function resolveMockProduct(status) {
    setRows((currentRows) =>
      currentRows.map((row) => (row.id === selectedMissing?.id ? { ...row, status, score: Math.max(row.score, 82) } : row)),
    );
    setSelectedMissing(null);
    setNotice("Eksik ürün eşleştirmesi yerel olarak güncellendi.");
  }

  async function resolveProduct(status, suggestion) {
    if (!isRealApiEnabled) {
      resolveMockProduct(status);
      return;
    }

    const item = selectedMissing;
    if (!item) return;
    if (status === "Eşleşti" && !suggestion?.product_id && !item.productId) {
      setApiError("Real API modunda eşleştirme için backend önerisinden ürün seçin.");
      return;
    }
    setSelectedMissing(null);
    await runRealAction(
      `resolve-${item.id}`,
      () => resolveCampaignItem(campaignId, item, status, suggestion),
      "Ürün eşleştirmesi güncellendi.",
    );
  }

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
            <Button
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
            </Button>
            <Button
              disabled={isLoading || actionLoading === "export-job"}
              onClick={() =>
                isRealApiEnabled
                  ? runRealAction(
                      "export-job",
                      () => createCampaignExportJob(campaignId),
                      "Çıktı işi kuyruğa alındı.",
                    )
                  : setNotice("Final dosyaları üretim için hazırlandı.")
              }
            >
              {actionLoading === "export-job" ? "Kuyruğa alınıyor..." : "Çıktı İşi Oluştur"}
            </Button>
            <Button variant="primary" onClick={() => setNotice("Dosya gönderimi bu fazda placeholder olarak kalıyor.")}>
              Kullanıcıya Gönder
            </Button>
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
            <dt>Ürün</dt>
            <dd>{campaign.productCount}</dd>
          </div>
          <div>
            <dt>Eşleşen</dt>
            <dd>{campaign.matchedCount ?? "-"}</dd>
          </div>
          <div>
            <dt>Eksik</dt>
            <dd>{campaign.missingCount ?? "-"}</dd>
          </div>
          <div>
            <dt>Düşük Güven</dt>
            <dd>{campaign.lowConfidenceCount ?? "-"}</dd>
          </div>
          <div>
            <dt>Güncelleme</dt>
            <dd>{campaign.updatedAtFull || campaign.updatedAt}</dd>
          </div>
        </dl>
      </section>

      <section className="dashboard-grid">
        <Card title="Broşür Önizleme" className="span-8">
          <PreviewFrame title={campaign.name} status="Placeholder önizleme" />
        </Card>

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
                    <Button onClick={() => setRows(rows.filter((row) => row.id !== product.id))}>Kampanyadan Çıkar</Button>
                  )}
                </div>
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
              "Öneriler",
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
              </tr>
            ))}
          </Table>
        </Card>

        <Card title="Çıktılar" className="span-12">
          <ExportPanel
            files={files}
            onAction={(message) =>
              isRealApiEnabled
                ? runRealAction("export-job", () => createCampaignExportJob(campaignId), "Çıktı işi kuyruğa alındı.")
                : setNotice(message)
            }
          />
        </Card>

        {isRealApiEnabled ? (
          <Card title="Çıktı İşleri" className="span-12">
            {exportJobs.length === 0 ? <p className="catalog-empty">Henüz çıktı işi yok.</p> : null}
            {exportJobs.length ? (
              <Table columns={["Tip", "Durum", "Formatlar", "Deneme", "Oluşturma"]}>
                {exportJobs.map((job) => (
                  <tr key={job.id}>
                    <td>{job.job_type}</td>
                    <td>
                      <StatusBadge status={job.status || "Bekliyor"} />
                    </td>
                    <td>{(job.requested_formats || []).join(", ") || "-"}</td>
                    <td>{job.attempts ?? 0}</td>
                    <td>{job.created_at || "-"}</td>
                  </tr>
                ))}
              </Table>
            ) : null}
          </Card>
        ) : null}

        <Card title="Mesaj Geçmişi" className="span-6">
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

        <Card title="İşlem Geçmişi" className="span-6">
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
    </>
  );
}
