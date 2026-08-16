import { useEffect, useState } from "react";
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
