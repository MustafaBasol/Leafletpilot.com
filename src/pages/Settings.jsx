import { useEffect, useRef, useState } from "react";
import { getSelectedMarketId } from "../api/authSession.js";
import { isRealApiEnabled } from "../api/config.js";
import { fetchMarketLogo, getMarketLogo, getMarketSettings, removeMarketLogo, updateMarketSettings, uploadMarketLogo } from "../api/marketApi.js";
import { Button, Card, Checkbox, Input, PageHeader } from "../components/ui/index.js";

const emptySettings = {
  name: "", address_line_1: "", address_line_2: "", postal_code: "", city: "", country_code: "FR",
  phone: "", website_url: "", instagram_url: "", facebook_url: "",
  brochure_preferences: { show_logo: true, show_address: false, show_phone: false, show_website: false, show_instagram: false, show_facebook: false },
  has_logo: false,
};

function LogoControl({ marketId, hasLogo, onChanged }) {
  const inputRef = useRef(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let objectUrl = "";
    async function load() {
      if (!isRealApiEnabled || !marketId) return;
      const status = await getMarketLogo(marketId);
      if (status?.has_logo) {
        objectUrl = URL.createObjectURL(await fetchMarketLogo(marketId));
        setUrl(objectUrl);
      } else setUrl("");
    }
    load().catch(() => setError("Logo yuklenemedi."));
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [marketId, hasLogo]);

  async function upload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 10 * 1024 * 1024) {
      setError("PNG, JPEG veya WebP (en fazla 10 MB) secin.");
      return;
    }
    try { setBusy(true); setError(""); await uploadMarketLogo(file, marketId); onChanged(); }
    catch (cause) { setError(cause.message || "Logo yuklenemedi."); }
    finally { setBusy(false); event.target.value = ""; }
  }
  async function remove() {
    try { setBusy(true); setError(""); await removeMarketLogo(marketId); onChanged(); }
    catch (cause) { setError(cause.message || "Logo kaldirilamadi."); }
    finally { setBusy(false); }
  }
  return <div className="settings-form">
    {url ? <img src={url} alt="Market logosu" style={{ maxWidth: 180, maxHeight: 80, objectFit: "contain" }} /> : <p>Logo yok; brosur market adiyla olusturulur.</p>}
    <input ref={inputRef} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={upload} aria-label="Market logosu yukle" />
    <div className="page-actions"><Button onClick={() => inputRef.current?.click()} disabled={busy}>{url ? "Logoyu degistir" : "Logo yukle"}</Button>{url ? <Button variant="danger" onClick={remove} disabled={busy}>Logoyu kaldir</Button> : null}</div>
    {error ? <p className="inline-result inline-result-warning" role="alert">{error}</p> : null}
  </div>;
}

export function Settings() {
  const marketId = getSelectedMarketId();
  const [settings, setSettings] = useState(emptySettings);
  const [loading, setLoading] = useState(isRealApiEnabled);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const load = async () => {
    if (!isRealApiEnabled) { setSettings(emptySettings); setLoading(false); return; }
    setLoading(true); setError("");
    try { setSettings({ ...emptySettings, ...(await getMarketSettings(marketId)) }); }
    catch (cause) { setError(cause.message || "Ayarlar yuklenemedi."); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [marketId]);
  const field = (name, value) => { setSettings((current) => ({ ...current, [name]: value })); setNotice(""); };
  const preference = (name, value) => { setSettings((current) => ({ ...current, brochure_preferences: { ...current.brochure_preferences, [name]: value } })); setNotice(""); };
  async function save() {
    const { id, has_logo, logo_mime_type, ...payload } = settings;
    void id; void has_logo; void logo_mime_type;
    try { setSaving(true); setError(""); const saved = await updateMarketSettings(payload, marketId); setSettings({ ...emptySettings, ...saved }); setNotice("Ayarlar kaydedildi."); }
    catch (cause) { setError(cause.message || "Ayarlar kaydedilemedi."); }
    finally { setSaving(false); }
  }

  return <>
    <PageHeader title="Ayarlar" description="Burada girdiginiz bilgiler yeni brosurlerde otomatik kullanilacaktir." actions={<Button variant="primary" onClick={save} disabled={loading || saving}>{saving ? "Kaydediliyor..." : "Kaydet"}</Button>} />
    {notice ? <p className="inline-result inline-result-success" role="status">{notice}</p> : null}
    {error ? <p className="inline-result inline-result-warning" role="alert">{error}</p> : null}
    <section className="dashboard-grid">
      <Card title="GENEL" className="span-8"><div className="form-grid">
        <Input label="Market adi" value={settings.name} onChange={(event) => field("name", event.target.value)} required />
        <Input label="Telefon" value={settings.phone || ""} onChange={(event) => field("phone", event.target.value)} />
        <Input label="Adres" value={settings.address_line_1 || ""} onChange={(event) => field("address_line_1", event.target.value)} />
        <Input label="Adres satiri 2" value={settings.address_line_2 || ""} onChange={(event) => field("address_line_2", event.target.value)} />
        <Input label="Posta kodu" value={settings.postal_code || ""} onChange={(event) => field("postal_code", event.target.value)} />
        <Input label="Sehir" value={settings.city || ""} onChange={(event) => field("city", event.target.value)} />
        <Input label={"\u00dclke kodu"} value={settings.country_code || ""} onChange={(event) => field("country_code", event.target.value)} maxLength="2" />
        <Input label="Web sitesi" type="url" value={settings.website_url || ""} onChange={(event) => field("website_url", event.target.value)} />
      </div></Card>
      <Card title="MARKA & SOSYAL" className="span-4"><LogoControl marketId={marketId} hasLogo={settings.has_logo} onChanged={load} /><div className="settings-form"><Input label="Instagram" value={settings.instagram_url || ""} onChange={(event) => field("instagram_url", event.target.value)} /><Input label="Facebook" value={settings.facebook_url || ""} onChange={(event) => field("facebook_url", event.target.value)} /><p className="table-hint">Instagram ve Facebook yalnizca brosurde goster etkinlestirildiginde eklenir.</p></div></Card>
      <Card title={"BRO\u015e\u00dcRDE G\u00d6STER"} className="span-12"><p className="table-hint">Market adi brosurlerde her zaman gosterilir. Diger bilgilerin gorunurlugunu buradan secebilirsiniz.</p><div className="checkbox-grid">
        <Checkbox label="Logo" checked={settings.brochure_preferences.show_logo} onChange={(event) => preference("show_logo", event.target.checked)} />
        <Checkbox label="Adres" checked={settings.brochure_preferences.show_address} onChange={(event) => preference("show_address", event.target.checked)} />
        <Checkbox label="Telefon" checked={settings.brochure_preferences.show_phone} onChange={(event) => preference("show_phone", event.target.checked)} />
        <Checkbox label="Web sitesi" checked={settings.brochure_preferences.show_website} onChange={(event) => preference("show_website", event.target.checked)} />
        <Checkbox label="Instagram" checked={settings.brochure_preferences.show_instagram} onChange={(event) => preference("show_instagram", event.target.checked)} />
        <Checkbox label="Facebook" checked={settings.brochure_preferences.show_facebook} onChange={(event) => preference("show_facebook", event.target.checked)} />
      </div></Card>
    </section>
  </>;
}