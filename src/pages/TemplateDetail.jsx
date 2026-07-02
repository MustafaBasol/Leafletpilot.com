import { useState } from "react";
import { findTemplateById, generatedFiles, outputFormats, products } from "../data/mockData.js";
import { Badge, Button, Card, ExportPanel, PageHeader, PreviewFrame, StatusBadge } from "../components/ui/index.js";

export function TemplateDetail({ templateId }) {
  const template = findTemplateById(templateId);
  const [message, setMessage] = useState("");
  const formats = outputFormats.filter((format) => template.formats.includes(format.label));

  return (
    <>
      <PageHeader
        title={template.name}
        description={`${template.type} · ${template.capacity} · ${template.formats.join(", ")}`}
        actions={
          <>
            <Button onClick={() => setMessage("Bu şablon varsayılan olarak işaretlendi.")}>Varsayılan Yap</Button>
            <Button onClick={() => setMessage("Önizleme oluşturma simüle edildi.")}>Önizleme Oluştur</Button>
            <Button onClick={() => setMessage("Şablon kopyası oluşturuldu.")}>Kopyala</Button>
            <Button variant="primary" onClick={() => setMessage("Düzenleme paneli bu fazda temsilidir.")}>
              Düzenle
            </Button>
          </>
        }
      />
      {message ? <p className="inline-result">{message}</p> : null}

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
        <Card title="Örnek Çıktılar" className="span-12">
          <ExportPanel files={generatedFiles} onAction={setMessage} />
        </Card>
      </section>
    </>
  );
}
