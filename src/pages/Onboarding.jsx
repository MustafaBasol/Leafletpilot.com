import { useEffect, useState } from "react";
import { onboardingApi } from "../api/onboardingApi.js";
import { listTemplates } from "../api/templateApi.js";
import { Button, Card } from "../components/ui/index.js";

export function Onboarding({ onCompleted }) {
  const [state, setState] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [form, setForm] = useState({});
  const [error, setError] = useState("");

  async function load() {
    try {
      const [onboarding, templateResponse] = await Promise.all([onboardingApi.get(), listTemplates({ active: true })]);
      setState(onboarding);
      setForm({
        display_name: onboarding.display_name || "",
        legal_name: onboarding.legal_name || "",
        country_code: onboarding.country_code || "FR",
        city: onboarding.city || "",
        language: onboarding.language || "tr",
        currency: onboarding.currency || "EUR",
        timezone: onboarding.timezone || "Europe/Paris",
        contact_email: onboarding.contact_email || "",
        contact_phone: onboarding.contact_phone || "",
        primary_color: onboarding.primary_color || "#16a34a",
        secondary_color: onboarding.secondary_color || "#f59e0b",
        default_template_id: onboarding.default_template_id || "",
      });
      setTemplates(templateResponse.items || []);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function saveProfile(event) {
    event.preventDefault();
    await onboardingApi.updateProfile({
      display_name: form.display_name,
      legal_name: form.legal_name || null,
      country_code: form.country_code,
      city: form.city || null,
      language: form.language,
      currency: form.currency,
      timezone: form.timezone,
      contact_email: form.contact_email || null,
      contact_phone: form.contact_phone || null,
    });
    await load();
  }

  async function saveBrand(event) {
    event.preventDefault();
    await onboardingApi.updateBrand({ primary_color: form.primary_color, secondary_color: form.secondary_color });
    await load();
  }

  async function saveTemplate(event) {
    event.preventDefault();
    await onboardingApi.updateTemplate({ default_template_id: form.default_template_id || null });
    await load();
  }

  async function complete() {
    await onboardingApi.complete();
    await load();
    onCompleted?.();
    window.location.hash = "#/dashboard";
  }

  const step = state?.onboarding_step || 1;

  return (
    <>
      <section className="page-heading">
        <div>
          <h2>Market Kurulumu</h2>
          <p>Temel profil, marka ve varsayılan şablon ayarlarını tamamlayın.</p>
        </div>
      </section>
      {error ? <p className="form-error">{error}</p> : null}
      <section className="dashboard-grid onboarding-grid">
        <Card title="1. Market Profili" className="span-6">
          <form className="settings-form" onSubmit={saveProfile}>
            {["display_name", "legal_name", "country_code", "city", "language", "currency", "timezone", "contact_email", "contact_phone"].map((field) => (
              <label key={field}>
                {field}
                <input value={form[field] || ""} onChange={(event) => update(field, event.target.value)} required={["display_name", "country_code", "language", "currency", "timezone"].includes(field)} />
              </label>
            ))}
            <Button variant="primary" type="submit">Profili Kaydet</Button>
          </form>
        </Card>
        <Card title="2. Marka" className="span-6">
          <form className="settings-form" onSubmit={saveBrand}>
            <label>Ana renk<input type="color" value={form.primary_color || "#16a34a"} onChange={(event) => update("primary_color", event.target.value)} /></label>
            <label>Vurgu rengi<input type="color" value={form.secondary_color || "#f59e0b"} onChange={(event) => update("secondary_color", event.target.value)} /></label>
            <div className="brand-preview" style={{ borderColor: form.primary_color, color: form.primary_color }}>
              Haftalık kampanya önizlemesi <span style={{ color: form.secondary_color }}>öne çıkan fiyat</span>
            </div>
            <Button variant="primary" type="submit" disabled={step < 2}>Markayı Kaydet</Button>
          </form>
        </Card>
        <Card title="3. Varsayılan Şablon" className="span-6">
          <form className="settings-form" onSubmit={saveTemplate}>
            {templates.length ? (
              <label>
                Şablon
                <select value={form.default_template_id || ""} onChange={(event) => update("default_template_id", event.target.value)}>
                  <option value="">Şablon seçmeden devam et</option>
                  {templates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}
                </select>
              </label>
            ) : (
              <p className="catalog-empty">Bu market için aktif şablon yok. Şablon seçmeden devam edebilirsiniz.</p>
            )}
            <Button variant="primary" type="submit" disabled={step < 3}>Şablonu Kaydet</Button>
          </form>
        </Card>
        <Card title="4. Tamamlama" className="span-6">
          <ul className="checklist">
            <li>Profil bilgileri</li>
            <li>Marka renkleri</li>
            <li>Varsayılan şablon tercihi</li>
            <li>Ürün importu ve Telegram bağlantısı sonraki adımlardır.</li>
          </ul>
          <Button variant="primary" onClick={complete} disabled={step < 4}>Kurulumu Tamamla</Button>
        </Card>
      </section>
    </>
  );
}
