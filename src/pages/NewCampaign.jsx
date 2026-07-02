import { useState } from "react";
import { markets, parsedWizardProducts, templates } from "../data/mockData.js";
import {
  Badge,
  Button,
  Card,
  Input,
  PageHeader,
  PreviewFrame,
  SelectPlaceholder,
  StatusBadge,
  Stepper,
  Table,
} from "../components/ui/index.js";

const steps = ["Bilgiler", "Ürün Listesi", "Eşleştirme", "Şablon", "Önizleme", "Çıktılar"];
const outputFormats = ["Baskı PDF", "PNG Broşür", "Instagram Post", "Instagram Story", "WhatsApp Görseli"];

const sampleList = `Coca Cola 2L - 1.59€
Eti Burçak - 0.99€
Torku Sucuk 400g - 5.99€
Ülker Halley - 1.49€`;

export function NewCampaign() {
  const [step, setStep] = useState(1);
  const [selectedTemplate, setSelectedTemplate] = useState(templates[0].id);
  const [selectedFormats, setSelectedFormats] = useState(["Baskı PDF", "PNG Broşür"]);
  const [campaignName, setCampaignName] = useState("Hafta 29 İndirimleri");

  function toggleFormat(format) {
    setSelectedFormats((current) =>
      current.includes(format) ? current.filter((item) => item !== format) : [...current, format],
    );
  }

  return (
    <>
      <PageHeader
        title="Yeni Kampanya"
        description="Panelden ürün listesi girerek broşür önizlemesi ve çıktı formatlarını hazırlayın."
        actions={
          <>
            <Button>Taslak Kaydet</Button>
            <Button variant="primary">Önizleme Oluştur</Button>
          </>
        }
      />

      <Card>
        <Stepper steps={steps} currentStep={step} />
      </Card>

      <section className="wizard-shell">
        <Card title={steps[step - 1]} className="wizard-main">
          {step === 1 ? (
            <div className="form-grid">
              <Input label="Kampanya Adı" value={campaignName} onChange={(event) => setCampaignName(event.target.value)} />
              <SelectPlaceholder label="Market" value={markets[0].name} />
              <Input label="Tarih Aralığı" value="01.07.2026 - 07.07.2026" readOnly />
              <SelectPlaceholder label="Kanal" value="Panel" />
              <SelectPlaceholder label="Şablon" value={templates[0].name} />
            </div>
          ) : null}

          {step === 2 ? (
            <div className="product-list-step">
              <label className="field field-full">
                <span>Ürün Listesi</span>
                <textarea defaultValue={sampleList} />
              </label>
              <div className="upload-zone">
                <strong>Excel veya PDF dosyası yükle</strong>
                <p>.xlsx, .csv veya .pdf dosyaları için görsel yükleme alanı. Bu fazda dosya işlenmez.</p>
              </div>
            </div>
          ) : null}

          {step === 3 ? (
            <Table columns={["Gelen Ürün", "Fiyat", "Eşleşen Ürün", "Güven", "Durum"]}>
              {parsedWizardProducts.map((product) => (
                <tr key={product.incomingName}>
                  <td>{product.incomingName}</td>
                  <td>{product.price}</td>
                  <td>{product.match}</td>
                  <td>
                    <Badge tone={product.score > 90 ? "success" : product.score > 70 ? "warning" : "danger"}>
                      %{product.score}
                    </Badge>
                  </td>
                  <td>
                    <StatusBadge status={product.status} />
                  </td>
                </tr>
              ))}
            </Table>
          ) : null}

          {step === 4 ? (
            <div className="template-grid">
              {templates.map((template) => (
                <button
                  className={`template-card ${selectedTemplate === template.id ? "is-selected" : ""}`.trim()}
                  type="button"
                  onClick={() => setSelectedTemplate(template.id)}
                  key={template.id}
                >
                  <div className="template-preview">{template.name.slice(0, 2)}</div>
                  <strong>{template.name}</strong>
                  <small>{template.type}</small>
                  <span>{template.capacity}</span>
                </button>
              ))}
            </div>
          ) : null}

          {step === 5 ? <PreviewFrame title={campaignName} status="Taslak önizleme" /> : null}

          {step === 6 ? (
            <div className="checkbox-grid">
              {outputFormats.map((format) => (
                <label className="check-row" key={format}>
                  <input
                    checked={selectedFormats.includes(format)}
                    type="checkbox"
                    onChange={() => toggleFormat(format)}
                  />
                  <span>{format}</span>
                </label>
              ))}
            </div>
          ) : null}
        </Card>

        <Card title="Kampanya Özeti" className="wizard-side">
          <dl className="detail-list">
            <div>
              <dt>Ad</dt>
              <dd>{campaignName}</dd>
            </div>
            <div>
              <dt>Market</dt>
              <dd>{markets[0].name}</dd>
            </div>
            <div>
              <dt>Ürün</dt>
              <dd>{parsedWizardProducts.length}</dd>
            </div>
            <div>
              <dt>Çıktı</dt>
              <dd>{selectedFormats.length} format</dd>
            </div>
          </dl>
          <div className="card-actions">
            <Button disabled={step === 1} onClick={() => setStep((current) => Math.max(1, current - 1))}>
              Geri
            </Button>
            <Button
              variant="primary"
              disabled={step === steps.length}
              onClick={() => setStep((current) => Math.min(steps.length, current + 1))}
            >
              İleri
            </Button>
          </div>
        </Card>
      </section>
    </>
  );
}
