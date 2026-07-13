import { useEffect, useMemo, useState } from "react";
import { isRealApiEnabled } from "../api/config.js";
import { markets, parsedWizardProducts, templates as mockTemplates } from "../data/mockData.js";
import { createCampaignFromText, getTemplates, parseCampaignTextPreview } from "../data/dataSource.js";
import { createCampaign, getCampaignBuilderOptions } from "../api/campaignApi.js";
import { getSelectedMarketId } from "../api/authSession.js";
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

function normalizeParsedItems(response) {
  if (Array.isArray(response)) return response;
  return response?.items || response?.parsed_items || [];
}

function formatParsedPrice(value, currency) {
  if (value === undefined || value === null || value === "") return "-";
  return `${value} ${currency || ""}`.trim();
}

export function NewCampaign() {
  const [step, setStep] = useState(1);
  const [templateItems, setTemplateItems] = useState(() => (isRealApiEnabled ? [] : mockTemplates));
  const [selectedTemplate, setSelectedTemplate] = useState(() => (isRealApiEnabled ? "" : mockTemplates[0].id));
  const [selectedFormats, setSelectedFormats] = useState(["Baskı PDF", "PNG Broşür"]);
  const [campaignName, setCampaignName] = useState("Hafta 29 İndirimleri");
  const [rawText, setRawText] = useState(sampleList);
  const [currency, setCurrency] = useState("EUR");
  const [language, setLanguage] = useState("tr");
  const [parsedItems, setParsedItems] = useState(parsedWizardProducts);
  const [apiError, setApiError] = useState("");
  const [notice, setNotice] = useState("");
  const [isParsing, setIsParsing] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [builderProducts, setBuilderProducts] = useState([]);
  const [selectedProducts, setSelectedProducts] = useState([]);
  const [builderConfig, setBuilderConfig] = useState({ headline: "", subtitle: "", footer: "" });

  const parsedCount = useMemo(() => parsedItems.length, [parsedItems]);
  const selectedTemplateItem = templateItems.find((template) => template.id === selectedTemplate) || templateItems[0];

  useEffect(() => {
    let isMounted = true;

    async function loadTemplates() {
      try {
        const response = isRealApiEnabled ? await getCampaignBuilderOptions(getSelectedMarketId()) : await getTemplates();
        const items = isRealApiEnabled ? (response?.templates || []) : response;
        if (!isMounted) return;
        setTemplateItems(items);
        if (isRealApiEnabled) {
          const availableProducts = response?.products || [];
          setBuilderProducts(availableProducts);
          setSelectedProducts(availableProducts.slice(0, 6));
        }
        setSelectedTemplate((current) => (items.some((template) => template.id === current) ? current : items[0]?.id || ""));
      } catch (error) {
        if (isMounted) {
          setTemplateItems([]);
          setSelectedTemplate("");
          setApiError(error.message || "Şablonlar yüklenemedi.");
        }
      }
    }

    loadTemplates();

    return () => {
      isMounted = false;
    };
  }, []);

  function toggleFormat(format) {
    setSelectedFormats((current) =>
      current.includes(format) ? current.filter((item) => item !== format) : [...current, format],
    );
  }

  async function parseText() {
    if (!isRealApiEnabled) return true;
    try {
      setIsParsing(true);
      setApiError("");
      const response = await parseCampaignTextPreview({ rawText, currency, language });
      setParsedItems(normalizeParsedItems(response));
      setNotice("Ürün listesi backend parser ile önizlendi.");
      return true;
    } catch (error) {
      setApiError(error.message || "Ürün listesi ayrıştırılamadı.");
      return false;
    } finally {
      setIsParsing(false);
    }
  }

  async function createCampaign() {
    if (!isRealApiEnabled) return;
    try {
      setIsCreating(true);
      setApiError("");
      const marketId = getSelectedMarketId();
      const items = selectedProducts.length
        ? selectedProducts.map((product, index) => ({ raw_line: product.name, incoming_name: product.name, display_name: product.name, market_product_id: product.id, currency: product.currency || currency, price: product.promo_price ?? product.regular_price, sort_order: index }))
        : null;
      const response = items
        ? await createCampaign({ title: campaignName, template_id: selectedTemplate || null, currency, language, items, builder_config: builderConfig }, marketId)
        : await createCampaignFromText({ title: campaignName, rawText, templateId: selectedTemplate, currency, language });
      const campaignId = response?.campaign_id || response?.campaign?.id;
      if (!campaignId) throw new Error("Backend kampanya kimliği döndürmedi.");
      window.location.hash = `#/campaigns/${campaignId}`;
    } catch (error) {
      setApiError(error.message || "Kampanya oluşturulamadı.");
    } finally {
      setIsCreating(false);
    }
  }

  async function goNext() {
    if (step === 2) {
      const parsed = await parseText();
      if (!parsed) return;
    }
    if (step === steps.length && isRealApiEnabled) {
      await createCampaign();
      return;
    }
    setStep((current) => Math.min(steps.length, current + 1));
  }

  return (
    <>
      <PageHeader
        title="Yeni Kampanya"
        description="Panelden ürün listesi girerek broşür önizlemesi ve çıktı formatlarını hazırlayın."
        actions={
          <>
            <Button onClick={() => setNotice("Taslak kaydetme bu fazda yerel olarak simüle edildi.")}>Taslak Kaydet</Button>
            <Button variant="primary" onClick={() => setStep(5)}>
              Önizleme Oluştur
            </Button>
          </>
        }
      />
      {notice ? <p className="inline-result">{notice}</p> : null}
      {apiError ? <p className="inline-result inline-result-warning">{apiError}</p> : null}

      <Card>
        <Stepper steps={steps} currentStep={step} />
      </Card>

      <section className="wizard-shell">
        <Card title={steps[step - 1]} className="wizard-main">
          {step === 1 ? (
            <div className="form-grid">
              <Input label="Kampanya Adı" value={campaignName} onChange={(event) => setCampaignName(event.target.value)} />
              <SelectPlaceholder label="Market" value={markets[0].name} />
              <Input label="Para Birimi" value={currency} onChange={(event) => setCurrency(event.target.value.toUpperCase())} />
              <Input label="Dil" value={language} onChange={(event) => setLanguage(event.target.value)} />
              <SelectPlaceholder label="Kanal" value="Panel" />
              <SelectPlaceholder label="Şablon" value={selectedTemplateItem?.name || "Şablon yok"} />
            </div>
          ) : null}

          {step === 2 ? (
            <div className="product-list-step">
              {isRealApiEnabled ? (
                <div className="template-grid">
                  {builderProducts.map((product) => {
                    const checked = selectedProducts.some((item) => item.id === product.id);
                    return <label className={`template-card ${checked ? "is-selected" : ""}`} key={product.id}><input type="checkbox" checked={checked} onChange={() => setSelectedProducts((current) => checked ? current.filter((item) => item.id !== product.id) : [...current, product])} /><strong>{product.name}</strong><small>{product.category || "Kategori yok"}</small><span>{product.promo_price ?? product.regular_price ?? "-"} {product.currency}</span></label>;
                  })}
                </div>
              ) : null}
              <label className="field field-full">
                <span>Ürün Listesi</span>
                <textarea value={rawText} onChange={(event) => setRawText(event.target.value)} />
              </label>
              <div className="upload-zone">
                <strong>Excel veya PDF dosyası yükle</strong>
                <p>.xlsx, .csv veya .pdf dosyaları için görsel yükleme alanı. Bu fazda dosya işlenmez.</p>
              </div>
              {isRealApiEnabled ? (
                <Button disabled={isParsing || !rawText.trim()} onClick={parseText}>
                  {isParsing ? "Ayrıştırılıyor..." : "Parser Önizleme"}
                </Button>
              ) : null}
            </div>
          ) : null}

          {step === 3 ? (
            <Table columns={["Ham Satır", "Gelen Ürün", "Fiyat", "Eski Fiyat", "Para Birimi", "Uyarılar"]}>
              {parsedItems.map((product, index) => (
                <tr key={`${product.raw_line || product.incomingName || product.incoming_name}-${index}`}>
                  <td>{product.raw_line || "-"}</td>
                  <td>{product.incoming_name || product.incomingName}</td>
                  <td>{formatParsedPrice(product.price, product.currency)}</td>
                  <td>{formatParsedPrice(product.old_price, product.currency)}</td>
                  <td>{product.currency || currency}</td>
                  <td>
                    {Array.isArray(product.warnings) && product.warnings.length ? (
                      product.warnings.join(", ")
                    ) : product.status ? (
                      <StatusBadge status={product.status} />
                    ) : (
                      "-"
                    )}
                  </td>
                </tr>
              ))}
            </Table>
          ) : null}

          {step === 4 ? (
            <div className="template-grid">
              {templateItems.map((template) => (
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
              {!templateItems.length ? <p className="catalog-empty">Şablon verisi gösterilemiyor.</p> : null}
            </div>
          ) : null}

          {step === 5 ? <PreviewFrame title={campaignName} status="Taslak önizleme" /> : null}

          {step === 6 ? (
            <div className="checkbox-grid">
              {outputFormats.map((format) => (
                <label className="check-row" key={format}>
                  <input checked={selectedFormats.includes(format)} type="checkbox" onChange={() => toggleFormat(format)} />
                  <span>{format}</span>
                </label>
              ))}
              {isRealApiEnabled ? <Badge tone="primary">Final aksiyon kampanyayı metinden oluşturur.</Badge> : null}
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
              <dd>{parsedCount}</dd>
            </div>
            <div>
              <dt>Çıktı</dt>
              <dd>{selectedFormats.length} format</dd>
            </div>
          </dl>
          <div className="card-actions">
            <Button disabled={step === 1 || isParsing || isCreating} onClick={() => setStep((current) => Math.max(1, current - 1))}>
              Geri
            </Button>
            <Button
              variant="primary"
              disabled={isParsing || isCreating || (!isRealApiEnabled && step === steps.length)}
              onClick={goNext}
            >
              {isParsing ? "Ayrıştırılıyor..." : isCreating ? "Oluşturuluyor..." : step === steps.length ? "Kampanyayı Oluştur" : "İleri"}
            </Button>
          </div>
        </Card>
      </section>
    </>
  );
}
