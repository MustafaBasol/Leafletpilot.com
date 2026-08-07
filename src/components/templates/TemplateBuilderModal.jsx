import { useEffect, useMemo, useState } from "react";
import { Button, Modal } from "../ui/index.js";

const DEFAULT_CONFIG = {
  layout: "promo-4", columns: 2, rows: 2, slot_count: 4, page_format: "a4_portrait",
  primary_color: "#c1121f", secondary_color: "#fffaf0", show_header_title: true,
  show_market_name: true, show_old_price: true, show_discount_badge: true,
  show_product_image: true, show_product_name: true, show_package_size: true,
  price_style: "bold", badge_style: "pill", show_footer: true,
};

const toggles = [
  ["show_header_title", "Başlık"], ["show_market_name", "Market adı"], ["show_old_price", "Eski fiyat"],
  ["show_discount_badge", "İndirim rozeti"], ["show_product_image", "Ürün görseli"],
  ["show_product_name", "Ürün adı"], ["show_package_size", "Paket boyutu"], ["show_footer", "Alt bilgi"],
];

function buildInitialForm(template) {
  return {
    name: template?.name || "", description: template?.description || "", category: template?.category || "Broşür",
    template_type: template?.template_type || "market", is_active: template?.is_active ?? true,
    config_json: { ...DEFAULT_CONFIG, ...(template?.config_json || {}) }, thumbnail: null,
  };
}

export function TemplateBuilderModal({ template, presets, busy, error, onClose, onSave }) {
  const targetKey = template?.id ? `edit:${template.id}` : "create";
  const initial = useMemo(() => buildInitialForm(template), [targetKey]);
  const [form, setForm] = useState(initial);
  const [submitted, setSubmitted] = useState(false);
  const dirty = JSON.stringify({ ...form, thumbnail: Boolean(form.thumbnail) }) !== JSON.stringify({ ...initial, thumbnail: false });
  const config = form.config_json;

  useEffect(() => {
    setForm(initial);
    setSubmitted(false);
  }, [initial]);

  useEffect(() => {
    const warn = (event) => { if (dirty) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function close() {
    if (!dirty || window.confirm("Kaydedilmemiş değişiklikler silinecek. Devam edilsin mi?")) onClose();
  }
  function field(key, value) { setForm((current) => ({ ...current, [key]: value })); }
  function configField(key, value) { setForm((current) => ({ ...current, config_json: { ...current.config_json, [key]: value } })); }
  function choosePreset(slug) {
    const preset = presets.items.find((item) => item.slug === slug);
    if (preset) setForm((current) => ({ ...current, config_json: { ...current.config_json, layout: slug, columns: preset.columns, rows: preset.rows, slot_count: preset.columns * preset.rows } }));
  }
  function submit(event) {
    event.preventDefault();
    if (busy) return;
    setSubmitted(true);
    if (!form.name.trim() || !form.category.trim()) return;
    onSave({ ...form, name: form.name.trim(), description: form.description.trim() || null, category: form.category.trim(), is_global: false });
  }

  return <Modal className="template-builder-modal" title={template ? "Şablonu düzenle" : "Özel şablon oluştur"} description="Ayarları değiştirirken gerçek düzenin canlı önizlemesini izleyin." onClose={close} footer={<><Button onClick={close} disabled={busy}>Vazgeç</Button><Button variant="primary" type="submit" form="template-builder-form" disabled={busy}>{busy ? "Kaydediliyor..." : "Kaydet"}</Button></>}>
    <div className="template-builder-layout">
      <form id="template-builder-form" className="template-builder-form" onSubmit={submit}>
        <label className="field"><span>Şablon adı *</span><input value={form.name} onChange={(e) => field("name", e.target.value)} aria-invalid={submitted && !form.name.trim()} required />{submitted && !form.name.trim() ? <small className="form-error">Şablon adı zorunludur.</small> : null}</label>
        <label className="field"><span>Açıklama</span><textarea value={form.description} onChange={(e) => field("description", e.target.value)} /></label>
        <div className="form-grid"><label className="field"><span>Kategori *</span><input value={form.category} onChange={(e) => field("category", e.target.value)} required /></label><label className="field"><span>Tür</span><select value={form.template_type} onChange={(e) => field("template_type", e.target.value)}><option value="market">Market broşürü</option><option value="flyer">El ilanı</option></select></label></div>
        <div className="form-grid"><label className="field"><span>Düzen</span><select value={config.layout} onChange={(e) => choosePreset(e.target.value)}>{presets.items.map((item) => <option key={item.slug} value={item.slug}>{item.name}</option>)}</select></label><label className="field"><span>Sayfa formatı</span><select value={config.page_format} onChange={(e) => configField("page_format", e.target.value)}>{presets.page_formats.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label></div>
        <div className="form-grid"><label className="field"><span>Sütun</span><input readOnly value={config.columns} /></label><label className="field"><span>Satır</span><input readOnly value={config.rows} /></label><label className="field"><span>Sayfa kapasitesi</span><input readOnly value={config.slot_count} /></label></div>
        <div className="form-grid"><label className="field"><span>Ana renk</span><input type="color" value={config.primary_color} onChange={(e) => configField("primary_color", e.target.value)} /></label><label className="field"><span>Arka plan</span><input type="color" value={config.secondary_color} onChange={(e) => configField("secondary_color", e.target.value)} /></label></div>
        <fieldset className="template-toggle-grid"><legend>Görünür alanlar</legend>{toggles.map(([key, label]) => <label key={key}><input type="checkbox" checked={config[key]} onChange={(e) => configField(key, e.target.checked)} /> {label}</label>)}</fieldset>
        <div className="form-grid"><label className="field"><span>Fiyat stili</span><select value={config.price_style} onChange={(e) => configField("price_style", e.target.value)}>{presets.price_styles.map((value) => <option key={value}>{value}</option>)}</select></label><label className="field"><span>Rozet stili</span><select value={config.badge_style} onChange={(e) => configField("badge_style", e.target.value)}>{presets.badge_styles.map((value) => <option key={value}>{value}</option>)}</select></label></div>
        <label className="field"><span>Küçük görsel (PNG, JPEG veya WebP)</span><input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => field("thumbnail", e.target.files?.[0] || null)} /></label>
        <label><input type="checkbox" checked={form.is_active} onChange={(e) => field("is_active", e.target.checked)} /> Şablon aktif</label>
        {error ? <p className="inline-result inline-result-warning">{error}</p> : null}
      </form>
      <div className="template-live-preview" style={{ "--template-primary": config.primary_color, "--template-background": config.secondary_color }}>
        <div className="template-preview-page">
          {config.show_header_title ? <header><small>{config.show_market_name ? "MARKETİNİZ" : ""}</small><strong>Haftanın Fırsatları</strong></header> : null}
          <div className="template-preview-products" style={{ gridTemplateColumns: `repeat(${config.columns}, 1fr)` }}>{Array.from({ length: config.slot_count }, (_, index) => <article key={index}>{config.show_discount_badge ? <b>FIRSAT</b> : null}{config.show_product_image ? <div className="template-preview-image">Ürün</div> : null}{config.show_product_name ? <span>Ürün adı</span> : null}{config.show_package_size ? <small>500 g</small> : null}<strong>49,90 ₺</strong>{config.show_old_price ? <del>59,90 ₺</del> : null}</article>)}</div>
          {config.show_footer ? <footer>Fiyatlar stoklarla sınırlıdır.</footer> : null}
        </div>
        <small>Canlı önizleme · {config.page_format === "a4_landscape" ? "A4 yatay" : "A4 dikey"} · {config.slot_count} ürün</small>
      </div>
    </div>
  </Modal>;
}
