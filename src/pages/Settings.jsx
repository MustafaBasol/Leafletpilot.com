import { useEffect, useRef, useState } from "react";
import { getSelectedMarketId } from "../api/authSession.js";
import { isRealApiEnabled } from "../api/config.js";
import { fetchMarketLogo, getMarketLogo, removeMarketLogo, uploadMarketLogo } from "../api/marketApi.js";
import { ApiStatus } from "../components/ApiStatus.jsx";
import { marketSettings, outputFormats, templates } from "../data/mockData.js";
import { getMarketPlan } from "../data/dataSource.js";
import { Button, Card, Checkbox, Input, PageHeader, SelectPlaceholder } from "../components/ui/index.js";

function formatLimit(value) {
  return value === null || value === undefined ? "Sınırsız" : value;
}

function PlanUsageCard() {
  const [plan, setPlan] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getMarketPlan()
      .then((response) => {
        if (!cancelled) setPlan(response);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  if (!plan) return null;

  return (
    <Card title="Plan / Kullanım" className="span-12">
      <div className="settings-form">
        <p>
          Mevcut plan: <strong>{plan.name}</strong>
        </p>
        <ul>
          <li>
            Aylık kampanya: {plan.monthly_campaigns_used} / {formatLimit(plan.monthly_campaigns_limit)}
          </li>
          <li>Aylık dışa aktarım limiti: {formatLimit(plan.monthly_exports_limit)}</li>
          <li>Özel ürün limiti: {formatLimit(plan.private_products_limit)}</li>
          <li>Özel şablon limiti: {formatLimit(plan.private_templates_limit)}</li>
          <li>Çıktı formatları: {(plan.export_formats || []).join(", ").toUpperCase()}</li>
        </ul>
      </div>
    </Card>
  );
}

function MarketLogoCard() {
  const inputRef = useRef(null);
  const [logoUrl, setLogoUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const marketId = getSelectedMarketId();
  async function load() {
    if (!isRealApiEnabled || !marketId) return;
    const status = await getMarketLogo(marketId);
    if (status?.has_logo) { const blob = await fetchMarketLogo(marketId); setLogoUrl(URL.createObjectURL(blob)); }
  }
  useEffect(() => { load().catch(() => setMessage("Logo yüklenemedi.")); return () => { if (logoUrl) URL.revokeObjectURL(logoUrl); }; }, [marketId]);
  async function upload(event) {
    const file = event.target.files?.[0]; if (!file) return;
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024) { setMessage('PNG veya JPEG logo (en fazla 10 MB) seçin.'); return; }
    try { setBusy(true); await uploadMarketLogo(file, marketId); await load(); setMessage('Market logosu güncellendi.'); } catch (error) { setMessage(error.message || 'Logo yüklenemedi.'); } finally { setBusy(false); event.target.value = ''; }
  }
  async function remove() { try { setBusy(true); await removeMarketLogo(marketId); setLogoUrl(''); setMessage('Market logosu kaldırıldı.'); } catch (error) { setMessage(error.message || 'Logo kaldırılamadı.'); } finally { setBusy(false); } }
  return <Card title="Market logosu" className="span-4"><div className="settings-form">{logoUrl ? <img src={logoUrl} alt="Market logosu" style={{ maxWidth: 180, maxHeight: 80, objectFit: 'contain' }} /> : <p>Logo yok; broşür market adıyla oluşturulur.</p>}<input ref={inputRef} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={upload} /><div className="page-actions"><Button onClick={() => inputRef.current?.click()} disabled={busy}>{logoUrl ? 'Logoyu değiştir' : 'Logo yükle'}</Button>{logoUrl ? <Button variant="danger" onClick={remove} disabled={busy}>Logoyu kaldır</Button> : null}</div>{message ? <p className="inline-result">{message}</p> : null}</div></Card>;
}
export function Settings() {
  const [settings, setSettings] = useState(marketSettings);
  const [saved, setSaved] = useState(false);

  function updateField(field, value) {
    setSettings((current) => ({ ...current, [field]: value }));
    setSaved(false);
  }

  function toggleFormat(label) {
    setSettings((current) => {
      const exists = current.defaultOutputFormats.includes(label);
      return {
        ...current,
        defaultOutputFormats: exists
          ? current.defaultOutputFormats.filter((format) => format !== label)
          : [...current.defaultOutputFormats, label],
      };
    });
    setSaved(false);
  }

  return (
    <>
      <PageHeader
        title="Ayarlar"
        description="Market marka bilgileri, varsayılan şablon ve çıktı tercihleri için basit frontend ayarları."
        actions={
          <Button variant="primary" onClick={() => setSaved(true)}>
            Kaydet
          </Button>
        }
      />
      {saved ? <p className="inline-result">Ayarlar yerel olarak kaydedildi.</p> : null}
      <section className="dashboard-grid">
        <Card title="Market Ayarları" className="span-8">
          <div className="settings-form">
            <div className="logo-placeholder">{settings.logoInitials}</div>
            <div className="form-grid">
              <Input label="Market adı" value={settings.marketName} onChange={(event) => updateField("marketName", event.target.value)} />
              <Input label="Ana renk" type="color" value={settings.primaryColor} onChange={(event) => updateField("primaryColor", event.target.value)} />
              <Input label="İkincil renk" type="color" value={settings.secondaryColor} onChange={(event) => updateField("secondaryColor", event.target.value)} />
              <SelectPlaceholder label="Varsayılan şablon" value={templates.find((template) => template.name === settings.defaultTemplate)?.name || settings.defaultTemplate} />
              <SelectPlaceholder label="Para birimi" value={settings.currency} />
              <SelectPlaceholder label="Dil" value={settings.language} />
            </div>
          </div>
        </Card>
        {isRealApiEnabled ? <MarketLogoCard /> : null}
        <Card title="Varsayılan Çıktılar" className="span-4">
          <div className="checkbox-grid single-column">
            {outputFormats.map((format) => (
              <Checkbox
                key={format.id}
                label={format.label}
                checked={settings.defaultOutputFormats.includes(format.label)}
                onChange={() => toggleFormat(format.label)}
              />
            ))}
          </div>
        </Card>
        <PlanUsageCard />
        <ApiStatus />
      </section>
    </>
  );
}
