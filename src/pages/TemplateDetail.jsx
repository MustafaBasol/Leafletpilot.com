import { useEffect, useState } from "react";
import { canManageTemplates, getSelectedMarketId } from "../api/authSession.js";
import { isRealApiEnabled } from "../api/config.js";
import { getTemplateDetail } from "../data/dataSource.js";
import { findTemplateById, generatedFiles, outputFormats, products } from "../data/mockData.js";
import { getTemplatePreviewHtml, getTemplatePresets, updateTemplate, uploadTemplateThumbnail } from "../api/templateApi.js";
import { Badge, Button, Card, ExportPanel, PageHeader, PreviewFrame, StatusBadge } from "../components/ui/index.js";
import { TemplateBuilderModal } from "../components/templates/TemplateBuilderModal.jsx";

function emptyTemplate(templateId) {
  return {
    id: templateId,
    name: "Şablon yükleniyor",
    type: "-",
    formats: [],
    capacity: "-",
    maxProductsPerPage: "-",
    status: "Pasif",
    isDefault: false,
    recommendation: "Şablon verisi henüz yüklenmedi.",
    bestFor: "-",
  };
}

export function TemplateDetail({ templateId }) {
  const [template, setTemplate] = useState(() => (isRealApiEnabled ? emptyTemplate(templateId) : findTemplateById(templateId)));
  const [message, setRawMessage] = useState("");
  const [apiError, setApiError] = useState("");
  const [preview, setPreview] = useState(null);
  const [previewError, setPreviewError] = useState("");
  const [isPreviewLoading, setPreviewLoading] = useState(false);
  const [isLoading, setIsLoading] = useState(isRealApiEnabled);
  const [isEditing, setEditing] = useState(false);
  const [isSaving, setSaving] = useState(false);
  const [presets, setPresets] = useState({ items: [], page_formats: [], price_styles: [], badge_styles: [] });
  const selectedMarketId = getSelectedMarketId();
  const canManage = canManageTemplates();
  const formats = outputFormats.filter((format) => template.formats.includes(format.label));

  function setMessage(nextMessage) {
    if (String(nextMessage).toLowerCase().includes("sim")) {
      loadPreview();
      return;
    }
    setRawMessage(nextMessage);
  }

  useEffect(() => {
    let isMounted = true;

    async function loadTemplate() {
      try {
        setIsLoading(isRealApiEnabled);
        if (isRealApiEnabled) setTemplate(emptyTemplate(templateId));
        const [detail, presetMetadata] = await Promise.all([getTemplateDetail(templateId), isRealApiEnabled ? getTemplatePresets(selectedMarketId) : Promise.resolve(null)]);
        if (isMounted) {
          setTemplate(detail);
          if (presetMetadata) setPresets(presetMetadata);
          setApiError("");
        }
      } catch (error) {
        if (isMounted) {
          setTemplate(emptyTemplate(templateId));
          setApiError(error.message || "Şablon detayı yüklenemedi.");
        }
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    loadTemplate();

    return () => {
      isMounted = false;
    };
  }, [templateId, selectedMarketId]);

  async function loadPreview() {
    if (!isRealApiEnabled) {
      setPreviewError("Gerçek şablon önizlemesi bağlı API ile kullanılabilir.");
      return;
    }
    setPreviewLoading(true);
    setPreviewError("");
    try {
      setPreview(await getTemplatePreviewHtml(templateId, selectedMarketId));
    } catch (error) {
      setPreview(null);
      setPreviewError(error.message || "Şablon önizlemesi oluşturulamadı. Ürün ve şablon erişimini kontrol edin.");
    } finally {
      setPreviewLoading(false);
    }
  }

  async function saveTemplate(form) {
    if (isSaving) return;
    setSaving(true);
    setApiError("");
    try {
      const { thumbnail, ...payload } = form;
      const saved = await updateTemplate(templateId, payload, selectedMarketId);
      if (thumbnail) await uploadTemplateThumbnail(templateId, thumbnail, selectedMarketId);
      setTemplate((current) => ({ ...current, name: saved.name, type: saved.template_type, recommendation: saved.description || "", status: saved.is_active ? "Aktif" : "Pasif", isGlobal: saved.is_global, raw: saved, capacity: `${saved.config_json?.slot_count || "-"} ürün`, maxProductsPerPage: saved.config_json?.slot_count || "-" }));
      setEditing(false);
      setRawMessage("Şablon değişiklikleri kaydedildi.");
      await loadPreview();
    } catch (error) {
      setApiError(error.status === 409 ? "Bu isimle bir şablon zaten mevcut." : (error.message || "Şablon kaydedilemedi."));
    } finally { setSaving(false); }
  }

  return (
    <>
      <PageHeader
        title={template.name}
        description={`${template.type} · ${template.capacity} · ${template.formats.join(", ")}`}
        actions={
          canManage ? (
            <>
              <Button onClick={() => setMessage("Bu şablon varsayılan olarak işaretlendi.")}>Varsayılan Yap</Button>
              <Button onClick={() => setMessage("Önizleme oluşturma simüle edildi.")}>Önizleme Oluştur</Button>
              <Button variant="primary" disabled={template.isGlobal} onClick={() => setEditing(true)}>
                Düzenle
              </Button>
            </>
          ) : null
        }
      />
      {message ? <p className="inline-result">{message}</p> : null}
      {apiError ? <p className="inline-result inline-result-warning">{apiError}</p> : null}
      {isLoading ? <p className="inline-result">Şablon detayı yükleniyor...</p> : null}

      <section className="detail-hero card">
        <div>
          <StatusBadge status={template.status} />
          <h2>{template.name}</h2>
          <p>{template.recommendation}</p>
          <div className="file-badges">
            {template.isDefault ? <Badge tone="primary">Varsayılan</Badge> : null}
            {template.formats.map((format) => (
              <span key={format}>{format}</span>
            ))}
          </div>
        </div>
        <dl className="summary-grid">
          <div>
            <dt>Şablon tipi</dt>
            <dd>{template.type}</dd>
          </div>
          <div>
            <dt>Maksimum ürün</dt>
            <dd>{template.maxProductsPerPage}</dd>
          </div>
          <div>
            <dt>En uygun market</dt>
            <dd>{template.bestFor}</dd>
          </div>
          <div>
            <dt>Varsayılan</dt>
            <dd>{template.isDefault ? "Evet" : "Hayır"}</dd>
          </div>
        </dl>
      </section>

      <section className="dashboard-grid">
        <Card title="Gerçek şablon önizlemesi" className="span-12">
          <Button onClick={loadPreview} disabled={isPreviewLoading}>Önizlemeyi yenile</Button>
          {isPreviewLoading ? <p className="inline-result">Gerçek önizleme oluşturuluyor...</p> : null}
          {previewError ? <p className="inline-result inline-result-warning">{previewError}</p> : null}
          {preview?.html ? <iframe className="campaign-preview-iframe" sandbox="" srcDoc={preview.html} title={`${template.name} gerçek önizleme`} /> : null}
        </Card>
        <Card title="Şablon Önizleme" className="span-8">
          <PreviewFrame title={template.name} status="Örnek veri" products={products.slice(0, 8)} formats={formats} />
        </Card>
        <Card title="Şablon Bilgileri" className="span-4">
          <dl className="detail-list">
            <div>
              <dt>Kullanım önerisi</dt>
              <dd>{template.recommendation}</dd>
            </div>
            <div>
              <dt>Ürün kapasitesi</dt>
              <dd>{template.capacity}</dd>
            </div>
            <div>
              <dt>Market tipi</dt>
              <dd>{template.bestFor}</dd>
            </div>
            <div>
              <dt>Formatlar</dt>
              <dd>{template.formats.join(", ")}</dd>
            </div>
          </dl>
        </Card>
        {!isRealApiEnabled ? (
          <Card title="Örnek Çıktılar" className="span-12">
            <ExportPanel files={generatedFiles} onAction={canManage ? setMessage : undefined} />
          </Card>
        ) : null}
      </section>
      {isEditing ? <TemplateBuilderModal template={template.raw || template} presets={presets} busy={isSaving} error={apiError} onClose={() => setEditing(false)} onSave={saveTemplate} /> : null}
    </>
  );
}
