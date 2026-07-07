import { useEffect, useState } from "react";
import { canManageTemplates, getSelectedMarketId } from "../api/authSession.js";
import { isRealApiEnabled } from "../api/config.js";
import { getTemplateDetail } from "../data/dataSource.js";
import { findTemplateById, generatedFiles, outputFormats, products } from "../data/mockData.js";
import { Badge, Button, Card, ExportPanel, PageHeader, PreviewFrame, StatusBadge } from "../components/ui/index.js";

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
  const [message, setMessage] = useState("");
  const [apiError, setApiError] = useState("");
  const [isLoading, setIsLoading] = useState(isRealApiEnabled);
  const selectedMarketId = getSelectedMarketId();
  const canManage = canManageTemplates();
  const formats = outputFormats.filter((format) => template.formats.includes(format.label));

  useEffect(() => {
    let isMounted = true;

    async function loadTemplate() {
      try {
        setIsLoading(isRealApiEnabled);
        if (isRealApiEnabled) setTemplate(emptyTemplate(templateId));
        const detail = await getTemplateDetail(templateId);
        if (isMounted) {
          setTemplate(detail);
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
              <Button onClick={() => setMessage("Şablon kopyası oluşturuldu.")}>Kopyala</Button>
              <Button variant="primary" onClick={() => setMessage("Düzenleme paneli bu fazda temsilidir.")}>
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
    </>
  );
}
