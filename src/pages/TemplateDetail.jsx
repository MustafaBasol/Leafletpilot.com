import { useEffect, useState } from "react";
import { isRealApiEnabled } from "../api/config.js";
import { getTemplateDetail } from "../data/dataSource.js";
import { findTemplateById, generatedFiles, outputFormats, products } from "../data/mockData.js";
import { Badge, Button, Card, ExportPanel, PageHeader, PreviewFrame, StatusBadge } from "../components/ui/index.js";

function emptyTemplate(templateId) {
  return {
    id: templateId,
    name: "Åžablon yÃ¼kleniyor",
    type: "-",
    formats: [],
    capacity: "-",
    maxProductsPerPage: "-",
    status: "Pasif",
    isDefault: false,
    recommendation: "Åžablon verisi henÃ¼z yÃ¼klenmedi.",
    bestFor: "-",
  };
}

export function TemplateDetail({ templateId }) {
  const [template, setTemplate] = useState(() => (isRealApiEnabled ? emptyTemplate(templateId) : findTemplateById(templateId)));
  const [message, setMessage] = useState("");
  const [apiError, setApiError] = useState("");
  const [isLoading, setIsLoading] = useState(isRealApiEnabled);
  const formats = outputFormats.filter((format) => template.formats.includes(format.label));

  useEffect(() => {
    let isMounted = true;

    async function loadTemplate() {
      try {
        setIsLoading(isRealApiEnabled);
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
  }, [templateId]);

  return (
    <>
      <PageHeader
        title={template.name}
        description={`${template.type} Â· ${template.capacity} Â· ${template.formats.join(", ")}`}
        actions={
          <>
            <Button onClick={() => setMessage("Bu ÅŸablon varsayÄ±lan olarak iÅŸaretlendi.")}>VarsayÄ±lan Yap</Button>
            <Button onClick={() => setMessage("Ã–nizleme oluÅŸturma simÃ¼le edildi.")}>Ã–nizleme OluÅŸtur</Button>
            <Button onClick={() => setMessage("Åžablon kopyasÄ± oluÅŸturuldu.")}>Kopyala</Button>
            <Button variant="primary" onClick={() => setMessage("DÃ¼zenleme paneli bu fazda temsilidir.")}>
              DÃ¼zenle
            </Button>
          </>
        }
      />
      {message ? <p className="inline-result">{message}</p> : null}
      {apiError ? <p className="inline-result inline-result-warning">{apiError}</p> : null}
      {isLoading ? <p className="inline-result">Åžablon detayÄ± yÃ¼kleniyor...</p> : null}

      <section className="detail-hero card">
        <div>
          <StatusBadge status={template.status} />
          <h2>{template.name}</h2>
          <p>{template.recommendation}</p>
          <div className="file-badges">
            {template.isDefault ? <Badge tone="primary">VarsayÄ±lan</Badge> : null}
            {template.formats.map((format) => (
              <span key={format}>{format}</span>
            ))}
          </div>
        </div>
        <dl className="summary-grid">
          <div>
            <dt>Åžablon tipi</dt>
            <dd>{template.type}</dd>
          </div>
          <div>
            <dt>Maksimum Ã¼rÃ¼n</dt>
            <dd>{template.maxProductsPerPage}</dd>
          </div>
          <div>
            <dt>En uygun market</dt>
            <dd>{template.bestFor}</dd>
          </div>
          <div>
            <dt>VarsayÄ±lan</dt>
            <dd>{template.isDefault ? "Evet" : "HayÄ±r"}</dd>
          </div>
        </dl>
      </section>

      <section className="dashboard-grid">
        <Card title="Åžablon Ã–nizleme" className="span-8">
          <PreviewFrame title={template.name} status="Ã–rnek veri" products={products.slice(0, 8)} formats={formats} />
        </Card>
        <Card title="Åžablon Bilgileri" className="span-4">
          <dl className="detail-list">
            <div>
              <dt>KullanÄ±m Ã¶nerisi</dt>
              <dd>{template.recommendation}</dd>
            </div>
            <div>
              <dt>ÃœrÃ¼n kapasitesi</dt>
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
        <Card title="Ã–rnek Ã‡Ä±ktÄ±lar" className="span-12">
          <ExportPanel files={generatedFiles} onAction={setMessage} />
        </Card>
      </section>
    </>
  );
}
