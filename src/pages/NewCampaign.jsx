import { useEffect, useMemo, useRef, useState } from "react";
import { isRealApiEnabled } from "../api/config.js";
import { getSelectedMarket, getSelectedMarketId, getStoredMarkets } from "../api/authSession.js";
import { createCampaign, createExportJob, finalizeCampaign, getCampaignBuilderOptions, getCampaignPreviewHtml, parseCampaignText, updateCampaign } from "../api/campaignApi.js";
import { getTemplatePreviewHtml } from "../api/templateApi.js";
import { Button, Card, Input, PageHeader, ProductThumbnail, Stepper, Table } from "../components/ui/index.js";

const steps = ["Bilgiler", "Ürün Listesi", "Eşleştirme", "Şablon", "Önizleme", "Çıktılar"];
const outputFormats = [
  { id: "pdf", label: "A4 PDF" },
  { id: "png", label: "A4 PNG" },
  { id: "instagram_post", label: "Instagram Post" },
  { id: "instagram_story", label: "Instagram Story" },
  { id: "whatsapp", label: "WhatsApp Görseli" },
];
const exportFormats = outputFormats.filter((format) => ["pdf", "png"].includes(format.id));
const channels = [{ id: "panel", label: "Panel" }, { id: "telegram", label: "Telegram" }, { id: "whatsapp", label: "WhatsApp" }, { id: "import", label: "İçe aktarım" }];
const errorText = (error) => error?.message || "İşlem tamamlanamadı.";

function catalogItemToPayload(product, index) {
  return { raw_line: product.name, incoming_name: product.name, market_product_id: product.id, sort_order: index };
}

export function NewCampaign() {
  const selectedMarketId = getSelectedMarketId();
  const storedMarket = getSelectedMarket();
  const marketOptions = getStoredMarkets();
  const [step, setStep] = useState(1);
  const [inputMode, setInputMode] = useState("catalog");
  const [templateItems, setTemplateItems] = useState([]);
  const [templatePreviews, setTemplatePreviews] = useState({});
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [selectedFormats, setSelectedFormats] = useState(["pdf", "png"]);
  const [previewFormat, setPreviewFormat] = useState("pdf");
  const [campaignName, setCampaignName] = useState("");
  const [currency, setCurrency] = useState(storedMarket?.currency || "EUR");
  const [language, setLanguage] = useState(storedMarket?.language || "tr");
  const [channel, setChannel] = useState("panel");
  const [rawText, setRawText] = useState("");
  const [parsedItems, setParsedItems] = useState([]);
  const [builderProducts, setBuilderProducts] = useState([]);
  const [builderLoading, setBuilderLoading] = useState(false);
  const [builderLoadError, setBuilderLoadError] = useState("");
  const [builderLoadAttempt, setBuilderLoadAttempt] = useState(0);
  const [selectedProducts, setSelectedProducts] = useState([]);
  const [productSearch, setProductSearch] = useState("");
  const [productCategory, setProductCategory] = useState("");
  const [productBrand, setProductBrand] = useState("");
  const [builderConfig, setBuilderConfig] = useState({ headline: "", subtitle: "", footer: "" });
  const [campaignId, setCampaignId] = useState("");
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const previewRequestRef = useRef(0);
  const [apiError, setApiError] = useState("");
  const [notice, setNotice] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  const activeProducts = useMemo(() => builderProducts.filter((product) => product.is_active !== false), [builderProducts]);
  const productCategories = useMemo(() => [...new Set(activeProducts.map((product) => product.category).filter(Boolean))].sort(), [activeProducts]);
  const productBrands = useMemo(() => [...new Set(activeProducts.map((product) => product.brand).filter(Boolean))].sort(), [activeProducts]);
  const visibleProducts = useMemo(() => {
    const query = productSearch.trim().toLocaleLowerCase("tr-TR");
    return activeProducts.filter((product) => {
      const haystack = [product.name, product.brand, product.category, product.package_size, product.package_type].filter(Boolean).join(" ").toLocaleLowerCase("tr-TR");
      return (!query || haystack.includes(query)) && (!productCategory || product.category === productCategory) && (!productBrand || product.brand === productBrand);
    });
  }, [activeProducts, productBrand, productCategory, productSearch]);
  const selectedTemplateItem = templateItems.find((template) => template.id === selectedTemplate);
  const selectedItems = inputMode === "catalog" ? selectedProducts : parsedItems;
  const selectedSlotCount = Number(selectedTemplateItem?.config_json?.slot_count || Number.POSITIVE_INFINITY);
  const slotValidation = selectedItems.length > selectedSlotCount;

  useEffect(() => {
    if (!isRealApiEnabled || !selectedMarketId) return undefined;
    let mounted = true;
    setBuilderLoading(true);
    setBuilderLoadError("");
    getCampaignBuilderOptions(selectedMarketId).then((response) => {
      if (!mounted) return;
      const templates = response?.templates || [];
      setTemplateItems(templates);
      setBuilderProducts( (response?.products || []).filter((product) => product.is_active !== false));
      setSelectedTemplate((current) => current && templates.some((template) => template.id === current) ? current : templates[0]?.id || "");
      Promise.all(templates.map(async (template) => {
        try { return [template.id, (await getTemplatePreviewHtml(template.id, selectedMarketId))?.html || ""]; } catch { return [template.id, ""]; }
      })).then((entries) => mounted && setTemplatePreviews(Object.fromEntries(entries)));
      setBuilderLoading(false);
    }).catch((error) => {
      if (!mounted) return;
      setBuilderLoading(false);
      setBuilderLoadError(errorText(error));
    });
    return () => { mounted = false; };
  }, [selectedMarketId, builderLoadAttempt]);

  const clearMessages = () => { setApiError(""); setNotice(""); };
  const toggleProduct = (product) => setSelectedProducts((current) => current.some((item) => item.id === product.id) ? current.filter((item) => item.id !== product.id) : [...current, product]);
  const clearSelectedProducts = () => setSelectedProducts([]);
  const toggleFormat = (format) => setSelectedFormats((current) => current.includes(format) ? current.filter((item) => item !== format) : [...current, format]);

  async function parseText() {
    if (!rawText.trim()) { setApiError("Metin listesi boş olamaz."); return false; }
    try {
      setIsBusy(true); clearMessages();
      const response = await parseCampaignText({ raw_text: rawText, default_currency: currency }, selectedMarketId);
      setParsedItems(response?.items || []); setNotice("Metin listesi ayrıştırıldı. Bu modda yalnızca ayrıştırılmış satırlar kullanılır."); return true;
    } catch (error) { setApiError(errorText(error)); return false; } finally { setIsBusy(false); }
  }

  async function persistDraft(format = previewFormat) {
    if (!campaignName.trim()) throw new Error("Kampanya adı zorunludur.");
    if (!selectedTemplate) throw new Error("Bir şablon seçin.");
    if (!selectedItems.length) throw new Error("En az bir ürün seçin veya metin listesi ayrıştırın.");
    if (slotValidation) throw new Error(`Seçili şablon en fazla ${selectedSlotCount} ürün destekliyor.`);
    const items = inputMode === "catalog" ? selectedProducts.map(catalogItemToPayload) : parsedItems.map((item, index) => ({ ...item, raw_line: item.raw_line || item.incoming_name, sort_order: index }));
    const payload = { title: campaignName, channel, source_type: inputMode === "catalog" ? "manual" : "text", raw_input_text: inputMode === "text" ? rawText : null, template_id: selectedTemplate, currency, language, items, builder_config: { ...builderConfig, output_format: format } };
    const response = campaignId ? await updateCampaign(campaignId, payload, selectedMarketId) : await createCampaign(payload, selectedMarketId);
    const id = response?.id || response?.campaign_id || response?.campaign?.id;
    if (!id) throw new Error("Backend yanıtında kampanya kimliği bulunamadı.");
    if (!campaignId) setCampaignId(id);
    return id;
  }

  async function loadPreview(format = previewFormat) {
    const requestId = ++previewRequestRef.current;
    setPreviewLoading(true); setPreviewError("");
    try {
      const id = await persistDraft(format);
      const response = await getCampaignPreviewHtml(id, selectedMarketId, { format, cache_bust: requestId });
      if (requestId !== previewRequestRef.current) return;
      setPreview(response); setNotice("Önizleme seçili ürünler ve şablonla backend tarafından oluşturuldu.");
    } catch (error) {
      if (requestId === previewRequestRef.current) setPreviewError(errorText(error));
      throw error;
    } finally {
      if (requestId === previewRequestRef.current) setPreviewLoading(false);
    }
  }

  async function saveDraft() {
    try { setIsBusy(true); clearMessages(); const id = await persistDraft(); setNotice(`Taslak kaydedildi: ${id}`); } catch (error) { setApiError(errorText(error)); } finally { setIsBusy(false); }
  }

  async function finishCampaign() {
    if (isBusy) return;
    try {
      setIsBusy(true); clearMessages(); const id = await persistDraft(); await finalizeCampaign(id, selectedMarketId);
      const formats = selectedFormats.filter((format) => exportFormats.some((item) => item.id === format));
      if (formats.length) await createExportJob(id, { job_type: "final_export", requested_formats: formats }, selectedMarketId);
      window.location.hash = `#/campaigns/${id}`;
    } catch (error) { setApiError(errorText(error)); } finally { setIsBusy(false); }
  }

  async function goNext() {
    if (isBusy) return;
    clearMessages();
    if (step === 1 && (!campaignName.trim() || !selectedTemplate || !channel)) { setApiError("Kampanya adı, kanal ve şablon zorunludur."); return; }
    if (step === 2 && inputMode === "text" && !(await parseText())) return;
    if (step === 4) { try { setIsBusy(true); await loadPreview(); } catch (error) { setApiError(errorText(error)); return; } finally { setIsBusy(false); } }
    if (step === steps.length) { await finishCampaign(); return; }
    setStep((current) => Math.min(steps.length, current + 1));
  }

  return <>
    <PageHeader title="Yeni Kampanya" description="Katalog ürünleri veya açıkça seçtiğiniz metin listesiyle kampanya oluşturun." actions={<Button onClick={saveDraft} disabled={isBusy}>Taslak Kaydet</Button>} />
    {notice ? <p className="inline-result">{notice}</p> : null}{apiError ? <p className="inline-result inline-result-warning">{apiError}</p> : null}
    <Card><Stepper steps={steps} currentStep={step} /></Card>
    <section className="wizard-shell"><Card title={steps[step - 1]} className="wizard-main">
      {step === 1 ? <div className="form-grid">
        <Input label="Kampanya Adı" value={campaignName} onChange={(event) => setCampaignName(event.target.value)} />
        <label className="field"><span>Market</span><select value={selectedMarketId} disabled><option value={selectedMarketId}>{storedMarket?.name || marketOptions.find((market) => market.id === selectedMarketId)?.name || "Seçili market"}</option></select></label>
        <label className="field"><span>Para Birimi</span><select value={currency} onChange={(event) => setCurrency(event.target.value)}><option value="EUR">EUR</option><option value="TRY">TRY</option><option value="USD">USD</option></select></label>
        <label className="field"><span>Dil</span><select value={language} onChange={(event) => setLanguage(event.target.value)}><option value="tr">Türkçe</option><option value="en">English</option></select></label>
        <label className="field"><span>Kanal</span><select value={channel} onChange={(event) => setChannel(event.target.value)}>{channels.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
        <label className="field"><span>Şablon</span><select value={selectedTemplate} onChange={(event) => setSelectedTemplate(event.target.value)}><option value="">Şablon seçin</option>{templateItems.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}</select></label>
      </div> : null}
      {step === 2 ? <div className="product-list-step">
        <div className="product-mode-selector" role="tablist" aria-label="Ürün kaynağı">
          <button type="button" role="tab" aria-selected={inputMode === "catalog"} className={inputMode === "catalog" ? "is-selected" : ""} onClick={() => setInputMode("catalog")}>Katalogdan seç</button>
          <button type="button" role="tab" aria-selected={inputMode === "text"} className={inputMode === "text" ? "is-selected" : ""} onClick={() => setInputMode("text")}>Metin listesi içe aktar</button>
        </div>
        {inputMode === "catalog" ? <>
          <div className="catalog-toolbar" aria-label="Katalog filtreleri">
            <label className="catalog-search"><span>Ürün ara</span><input type="search" value={productSearch} onChange={(event) => setProductSearch(event.target.value)} placeholder="Ürün, marka veya paket ara" /></label>
            {productCategories.length ? <label className="catalog-filter"><span>Kategori</span><select value={productCategory} onChange={(event) => setProductCategory(event.target.value)}><option value="">Tüm kategoriler</option>{productCategories.map((category) => <option key={category} value={category}>{category}</option>)}</select></label> : null}
            {productBrands.length ? <label className="catalog-filter"><span>Marka</span><select value={productBrand} onChange={(event) => setProductBrand(event.target.value)}><option value="">Tüm markalar</option>{productBrands.map((brand) => <option key={brand} value={brand}>{brand}</option>)}</select></label> : null}
            <div className="catalog-toolbar-meta"><strong>{selectedProducts.length} ürün seçildi</strong><button type="button" className="text-button" onClick={clearSelectedProducts} disabled={!selectedProducts.length}>Seçimi temizle</button></div>
          </div>
          {builderLoading ? <div className="product-grid product-grid-skeleton" aria-label="Ürünler yükleniyor">{Array.from({ length: 8 }, (_, index) => <div className="product-skeleton" key={index}><span /><b /><i /></div>)}</div> : builderLoadError ? <div className="catalog-state"><strong>Katalog yüklenemedi.</strong><p>{builderLoadError}</p><Button onClick={() => setBuilderLoadAttempt((attempt) => attempt + 1)}>Tekrar dene</Button></div> : !activeProducts.length ? <div className="catalog-state"><strong>Bu markette aktif ürün yok.</strong><p>Kampanyaya ürün eklemek için önce kataloğunuza aktif ürün ekleyin.</p></div> : !visibleProducts.length ? <div className="catalog-state"><strong>Sonuç bulunamadı.</strong><p>Arama veya filtreleri değiştirerek tekrar deneyin.</p></div> : <div className="product-grid">{visibleProducts.map((product) => { const checked = selectedProducts.some((item) => item.id === product.id); return <button type="button" className={`product-card ${checked ? "is-selected" : ""}`} aria-pressed={checked} onClick={() => toggleProduct(product)} key={product.id}><span className="product-card-check" aria-hidden="true">{checked ? "✓" : ""}</span><ProductThumbnail label={product.name} hasImage={Boolean(product.image_url)} imageUrl={product.image_url} marketId={selectedMarketId} refreshKey={product.image_url} size="lg" /><strong>{product.name}</strong><small>{product.brand || "Marka belirtilmedi"}</small><small>{[product.package_size, product.package_type].filter(Boolean).join(" · ") || "Paket belirtilmedi"}</small><span className="product-card-price"><b>{product.promo_price ?? product.regular_price ?? "-"} {product.currency}</b>{product.promo_price && product.regular_price && product.promo_price !== product.regular_price ? <del>{product.regular_price} {product.currency}</del> : null}</span></button>; })}</div>}
          <div className="selection-summary" aria-label="Ürün seçimi özeti"><div><strong>{selectedProducts.length} ürün seçildi</strong><div className="selection-thumbnails">{selectedProducts.slice(0, 5).map((product) => <ProductThumbnail key={product.id} label={product.name} hasImage={Boolean(product.image_url)} imageUrl={product.image_url} marketId={selectedMarketId} refreshKey={product.image_url} size="sm" />)}{selectedProducts.length > 5 ? <span className="selection-more">+{selectedProducts.length - 5}</span> : null}</div></div><div className="selection-actions"><button type="button" className="text-button" onClick={clearSelectedProducts} disabled={!selectedProducts.length}>Tümünü temizle</button><Button disabled={isBusy || !selectedProducts.length || slotValidation} onClick={goNext} variant="primary">İleri</Button></div></div>
        </> : <label className="field field-full"><span>Metin listesi</span><textarea value={rawText} onChange={(event) => setRawText(event.target.value)} placeholder="Örn. Süt 1L - 1,59 EUR" /><Button onClick={parseText} disabled={isBusy || !rawText.trim()}>Parser ile ayrıştır</Button></label>}
      </div> : null}
      {step === 3 ? <Table columns={inputMode === "catalog" ? ["Ürün", "Fiyat", "Eski fiyat", "Para birimi", "Paket"] : ["Ham satır", "Gelen ürün", "Fiyat", "Eski fiyat", "Uyarılar"]}>{selectedItems.map((product, index) => <tr key={product.id || `${product.raw_line}-${index}`}><td>{product.name || product.incoming_name}</td><td>{product.promo_price ?? product.price ?? "-"} {product.currency || currency}</td><td>{product.regular_price ?? product.old_price ?? "-"}</td>{inputMode === "catalog" ? <><td>{product.currency}</td><td>{[product.package_size, product.package_type].filter(Boolean).join(" ") || "-"}</td></> : <td>{product.warnings?.join(", ") || "-"}</td>}</tr>)}</Table> : null}
      {step === 4 ? <div className="template-grid">{templateItems.map((template) => <button className={`template-card template-gallery-card ${selectedTemplate === template.id ? "is-selected" : ""}`} type="button" onClick={() => setSelectedTemplate(template.id)} key={template.id}><div className="template-thumbnail">{templatePreviews[template.id] ? <iframe title={`${template.name} önizlemesi`} srcDoc={templatePreviews[template.id]} sandbox="" scrolling="no" tabIndex="-1" aria-hidden="true" /> : <div className="template-preview-fallback">{template.name.slice(0, 2)}</div>}</div><strong>{template.name}</strong><small>{template.template_type || "Broşür"}</small><span>{template.config_json?.slot_count || "Sınırsız"} ürün</span></button>)}</div> : null}
      {step === 5 ? <div className="stack-list"><label className="field"><span>Önizleme boyutu</span><select value={previewFormat} onChange={async (event) => { const value = event.target.value; setPreviewFormat(value); try { setIsBusy(true); await loadPreview(value); } catch (error) { setApiError(errorText(error)); } finally { setIsBusy(false); } }}>{outputFormats.map((format) => <option key={format.id} value={format.id}>{format.label}</option>)}</select></label>{previewLoading ? <p className="inline-result">Önizleme yenileniyor...</p> : null}{previewError ? <p className="inline-result inline-result-warning">{previewError}</p> : null}{preview?.html ? <div className={`campaign-preview-viewport preview-format-${previewFormat}`}><iframe className="campaign-preview-frame" title="Kampanya önizlemesi" srcDoc={preview.html} sandbox="" scrolling="no" /></div> : <p>Önizleme henüz oluşturulmadı.</p>}<div className="form-grid"><Input label="Başlık" value={builderConfig.headline} onChange={(event) => setBuilderConfig((current) => ({ ...current, headline: event.target.value }))} /><Input label="Alt başlık" value={builderConfig.subtitle} onChange={(event) => setBuilderConfig((current) => ({ ...current, subtitle: event.target.value }))} /><Input label="Alt bilgi" value={builderConfig.footer} onChange={(event) => setBuilderConfig((current) => ({ ...current, footer: event.target.value }))} /></div><Button onClick={async () => { try { setIsBusy(true); await loadPreview(); } catch (error) { setApiError(errorText(error)); } finally { setIsBusy(false); } }} disabled={isBusy}>{previewLoading ? "Yenileniyor..." : "Önizlemeyi yenile"}</Button></div> : null}
      {step === 6 ? <div className="checkbox-grid">{outputFormats.map((format) => <label className="check-row" key={format.id}><input checked={selectedFormats.includes(format.id)} type="checkbox" onChange={() => toggleFormat(format.id)} /><span>{format.label}</span></label>)}</div> : null}
      </Card>{step !== 2 ? <Card title="Kampanya Özeti" className="wizard-side"><dl className="detail-list"><div><dt>Ad</dt><dd>{campaignName || "-"}</dd></div><div><dt>Market</dt><dd>{storedMarket?.name || "-"}</dd></div><div><dt>Girdi modu</dt><dd>{inputMode === "catalog" ? "Katalog" : "Metin"}</dd></div><div><dt>Ürün</dt><dd>{selectedItems.length}</dd></div><div><dt>Çıktı</dt><dd>{selectedFormats.length} format</dd></div></dl><div className="card-actions"><Button disabled={step === 1 || isBusy} onClick={() => setStep((current) => Math.max(1, current - 1))}>Geri</Button><Button variant="primary" disabled={isBusy || slotValidation} onClick={goNext}>{isBusy ? "Kaydediliyor..." : step === steps.length ? "Kampanyayı Oluştur" : "İleri"}</Button></div></Card> : null}</section>
  </>;
}
