import { useState } from "react";
import { ApiStatus } from "../components/ApiStatus.jsx";
import { marketSettings, outputFormats, templates } from "../data/mockData.js";
import { Button, Card, Checkbox, Input, PageHeader, SelectPlaceholder } from "../components/ui/index.js";

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
        <ApiStatus />
      </section>
    </>
  );
}
