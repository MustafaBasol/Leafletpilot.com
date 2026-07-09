import { useState } from "react";
import { submitSignupRequest } from "../api/publicApi.js";

const initialForm = {
  market_name: "",
  contact_name: "",
  email: "",
  phone: "",
  country_code: "FR",
  city: "",
  preferred_language: "tr",
  expected_campaigns_per_month: "",
  notes: "",
  consent_accepted: false,
  website: "",
};

export function Start() {
  const [form, setForm] = useState(initialForm);
  const [state, setState] = useState({ loading: false, success: "", error: "" });

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    setState({ loading: true, success: "", error: "" });
    try {
      const payload = {
        ...form,
        expected_campaigns_per_month: form.expected_campaigns_per_month ? Number(form.expected_campaigns_per_month) : null,
      };
      const response = await submitSignupRequest(payload);
      setForm(initialForm);
      setState({ loading: false, success: response.message, error: "" });
    } catch (error) {
      setState({ loading: false, success: "", error: error.message || "Başvuru gönderilemedi." });
    }
  }

  return (
    <main className="public-page">
      <a className="brand public-brand" href="#/">
        <span className="brand-mark">LP</span>
        <span>
          <strong>LeafletPilot</strong>
          <small>Ücretsiz deneme başvurusu</small>
        </span>
      </a>
      <section className="public-form-shell">
        <div className="public-copy">
          <span className="landing-eyebrow">Kontrollü başlangıç</span>
          <h1>Marketiniz için ücretsiz deneme başvurusu</h1>
          <p>
            Başvurunuzu aldıktan sonra LeafletPilot ekibi uygun kurulum adımlarını sizinle paylaşır. Bu form hesap
            oluşturmaz ve otomatik onay vermez.
          </p>
        </div>
        <form className="public-form" onSubmit={submit}>
          <input
            className="honeypot"
            tabIndex="-1"
            autoComplete="off"
            value={form.website}
            onChange={(event) => update("website", event.target.value)}
            aria-hidden="true"
          />
          <label>
            Market adı
            <input required autoComplete="organization" value={form.market_name} onChange={(event) => update("market_name", event.target.value)} />
          </label>
          <label>
            Yetkili adı soyadı
            <input required autoComplete="name" value={form.contact_name} onChange={(event) => update("contact_name", event.target.value)} />
          </label>
          <label>
            E-posta
            <input required type="email" autoComplete="email" value={form.email} onChange={(event) => update("email", event.target.value)} />
          </label>
          <label>
            Telefon
            <input autoComplete="tel" value={form.phone} onChange={(event) => update("phone", event.target.value)} />
          </label>
          <label>
            Ülke
            <input required maxLength="2" value={form.country_code} onChange={(event) => update("country_code", event.target.value.toUpperCase())} />
          </label>
          <label>
            Şehir
            <input autoComplete="address-level2" value={form.city} onChange={(event) => update("city", event.target.value)} />
          </label>
          <label>
            Tercih edilen dil
            <select value={form.preferred_language} onChange={(event) => update("preferred_language", event.target.value)}>
              <option value="tr">Türkçe</option>
              <option value="fr">Français</option>
              <option value="en">English</option>
            </select>
          </label>
          <label>
            Aylık tahmini kampanya sayısı
            <input min="0" max="1000" type="number" value={form.expected_campaigns_per_month} onChange={(event) => update("expected_campaigns_per_month", event.target.value)} />
          </label>
          <label className="span-2">
            Not
            <textarea maxLength="2000" rows="4" value={form.notes} onChange={(event) => update("notes", event.target.value)} />
          </label>
          <label className="checkbox-line span-2">
            <input required type="checkbox" checked={form.consent_accepted} onChange={(event) => update("consent_accepted", event.target.checked)} />
            Başvurumun değerlendirilmesi için iletişim bilgilerimin LeafletPilot tarafından kullanılmasını kabul ediyorum.
          </label>
          {state.error ? <p className="inline-result inline-result-warning span-2">{state.error}</p> : null}
          {state.success ? <p className="inline-result span-2">{state.success}</p> : null}
          <button className="landing-btn landing-btn-primary landing-btn-lg span-2" type="submit" disabled={state.loading}>
            {state.loading ? "Gönderiliyor..." : "Başvuru Gönder"}
          </button>
        </form>
      </section>
    </main>
  );
}
