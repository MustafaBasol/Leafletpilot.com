import { useEffect, useRef, useState } from "react";
import { canManageTemplates, getSelectedMarketId } from "../api/authSession.js";
import { isRealApiEnabled } from "../api/config.js";
import { outputFormats, templates as mockTemplates } from "../data/mockData.js";
import { getTemplates, updateTemplateStatus } from "../data/dataSource.js";
import { adoptTemplate, createCustomTemplate, getMyTemplates, getSharedTemplates, getTemplatePresets, updateTemplate, uploadTemplateThumbnail } from "../api/templateApi.js";
import { Button, ConfirmDialog, FilterBar, FilterChip, PageHeader, TemplateCard } from "../components/ui/index.js";
import { TemplateBuilderModal } from "../components/templates/TemplateBuilderModal.jsx";

const fallbackPresets = { items: [{ slug: "promo-4", name: "Promo 4", columns: 2, rows: 2 }], page_formats: [{ value: "a4_portrait", label: "A4 dikey" }], price_styles: ["bold"], badge_styles: ["pill"] };

export function Templates() {
  const [items, setItems] = useState(() => (isRealApiEnabled ? [] : mockTemplates));
  const [apiError, setApiError] = useState("");
  const [isLoading, setIsLoading] = useState(isRealApiEnabled);
  const [shared, setShared] = useState([]);
  const [mine, setMine] = useState([]);
  const [actionError, setActionError] = useState("");
  const [confirmTemplate, setConfirmTemplate] = useState(null);
  const [builderTemplate, setBuilderTemplate] = useState(undefined);
  const [presets, setPresets] = useState(fallbackPresets);
  const [isSaving, setSaving] = useState(false);
  const [success, setSuccess] = useState("");
  const submittingRef = useRef(false);
  const selectedMarketId = getSelectedMarketId();
  const canManage = canManageTemplates();

  async function loadTemplates() {
    try {
      setIsLoading(isRealApiEnabled);
      if (isRealApiEnabled) setItems([]);
      const templates = await getTemplates();
      setItems(templates);
      if (isRealApiEnabled) {
        const [sharedResult, mineResult, presetResult] = await Promise.all([getSharedTemplates(selectedMarketId), getMyTemplates(selectedMarketId), getTemplatePresets(selectedMarketId)]);
        setShared(sharedResult.items || []);
        setMine(mineResult.items || []);
        setPresets(presetResult);
      }
      setApiError("");
    } catch (error) {
      setItems([]);
      setApiError(error.message || "Şablonlar yüklenemedi.");
    } finally {
      setIsLoading(false);
    }
  }

  async function addShared(template) {
    try {
      await adoptTemplate(template.id, selectedMarketId);
      setActionError("");
      await loadTemplates();
    } catch (error) { setActionError(error.message || "Şablon eklenemedi."); }
  }

  async function saveBuilder(form) {
    if (submittingRef.current) return;
    submittingRef.current = true;
    setSaving(true);
    try {
      const { thumbnail, ...payload } = form;
      const saved = builderTemplate ? await updateTemplate(builderTemplate.id, payload, selectedMarketId) : await createCustomTemplate(payload, selectedMarketId);
      if (thumbnail) await uploadTemplateThumbnail(saved.id, thumbnail, selectedMarketId);
      setActionError("");
      await loadTemplates();
      setBuilderTemplate(undefined);
      setSuccess(`${saved.name} şablonu kaydedildi ve seçildi.`);
    } catch (error) {
      setActionError(error.status === 409 ? "Bu isimle bir şablon zaten mevcut." : (error.message || "Şablon kaydedilemedi."));
    } finally {
      submittingRef.current = false;
      setSaving(false);
    }
  }

  useEffect(() => {
    loadTemplates();
  }, [selectedMarketId]);

  function makeDefault(id) {
    if (!canManage) return;
    setItems((current) => current.map((template) => ({ ...template, isDefault: template.id === id })));
  }

  function duplicateTemplate(id) {
    if (!canManage) return;
    const source = items.find((template) => template.id === id);
    if (!source) return;
    setItems((current) => [
      ...current,
      {
        ...source,
        id: `${source.id}-copy-${current.length}`,
        name: `${source.name} Kopya`,
        isDefault: false,
        status: "Pasif",
      },
    ]);
  }

  async function toggleStatus(template) {
    if (!template || !canManage) return;
    const nextStatus = template.status === "Aktif" ? "Pasif" : "Aktif";

    if (isRealApiEnabled) {
      try {
        await updateTemplateStatus(template.id, nextStatus === "Aktif");
        await loadTemplates();
        return;
      } catch (error) {
        setApiError(error.message || "Şablon durumu güncellenemedi.");
        return;
      }
    }

    setItems((current) =>
      current.map((item) => (item.id === template.id ? { ...item, status: nextStatus, isDefault: false } : item)),
    );
  }

  async function confirmToggleStatus() {
    const template = confirmTemplate;
    setConfirmTemplate(null);
    await toggleStatus(template);
  }

  return (
    <>
      <PageHeader
        title="Şablonlar"
        description="Broşür üretiminde kullanılacak profesyonel düzenleri, format desteğini ve varsayılan seçimleri yönetin."
      />
      <FilterBar placeholder="Şablon adı, tip veya kullanım önerisi ara">
        <FilterChip label="Şablon tipi" value="Tüm tipler" />
        <FilterChip label="Durum" value="Aktif ve pasif" />
        <FilterChip label="Format" value={outputFormats[0].label} />
      </FilterBar>
      {apiError ? <p className="inline-result inline-result-warning">{apiError}</p> : null}
      {actionError ? <p className="inline-result inline-result-warning">{actionError}</p> : null}
      {success ? <p className="inline-result">{success}</p> : null}
      {isLoading ? <p className="inline-result">Şablonlar yükleniyor...</p> : null}
      {!isLoading && items.length === 0 ? <p className="catalog-empty">Şablon verisi gösterilemiyor.</p> : null}
      {isRealApiEnabled ? (
        <>
          <section className="card" style={{ marginBottom: 24 }}>
            <h2>Global şablonlar</h2>
            <p>Planınıza uygun global şablonları marketinize ekleyin.</p>
            <div className="template-management-grid">
              {shared.map((template) => {
                const added = mine.some((item) => item.source_template_id === template.id);
                return <article className="card template-real-card" key={template.id}><span className="template-source">Global</span><h3>{template.name}</h3><p>{template.description || ""}</p><small>{template.config_json?.page_format === "a4_landscape" ? "A4 yatay" : "A4 dikey"} · {template.config_json?.slot_count || "-"} ürün</small><div className="table-actions"><Button onClick={() => { window.location.href = `/templates/${template.id}`; }}>Önizle</Button><Button variant="primary" onClick={() => addShared(template)} disabled={added}>{added ? "Eklendi" : "Marketime ekle"}</Button></div></article>;
              })}
            </div>
          </section>
          <section className="card" style={{ marginBottom: 24 }}><h2>Özel şablon oluştur</h2><p>Planınız izin veriyorsa marketinize özel bir şablon oluşturabilirsiniz.</p><Button variant="primary" disabled={!canManage} onClick={() => { setActionError(""); setBuilderTemplate(null); }}>Özel şablon oluştur</Button></section>
          <section className="card" style={{ marginBottom: 24 }}><h2>Marketimin şablonları</h2><div className="template-management-grid">{mine.map((template) => <article className="card template-real-card" key={template.id}><span className="template-source">{template.source_template_id ? "Globalden kopyalandı" : "Markete özel"}</span><h3>{template.name}</h3><p>{template.description || ""}</p><small>{template.config_json?.page_format === "a4_landscape" ? "A4 yatay" : "A4 dikey"} · {template.config_json?.slot_count || "-"} ürün · {template.is_active ? "Aktif" : "Pasif"}</small><div className="table-actions"><Button onClick={() => { window.location.href = `/templates/${template.id}`; }}>Önizle</Button>{canManage ? <><Button variant="primary" onClick={() => { setActionError(""); setBuilderTemplate(template); }}>Düzenle</Button><Button onClick={async () => { await updateTemplate(template.id, { is_active: !template.is_active }, selectedMarketId); await loadTemplates(); }}>{template.is_active ? "Pasifleştir" : "Aktifleştir"}</Button></> : null}</div></article>)}</div></section>
        </>
      ) : null}
      <section className="template-management-grid">
        {items.map((template) => (
          <TemplateCard
            key={template.id}
            template={template}
            onMakeDefault={makeDefault}
            onDuplicate={duplicateTemplate}
            onToggle={() => setConfirmTemplate(template)}
            canManage={canManage}
          />
        ))}
      </section>
      <ConfirmDialog
        isOpen={Boolean(confirmTemplate)}
        title="Şablon durumunu değiştir"
        description={
          confirmTemplate
            ? `${confirmTemplate.name} şablonu ${confirmTemplate.status === "Aktif" ? "pasifleştirilecek" : "aktifleştirilecek"}. Devam edilsin mi?`
            : ""
        }
        confirmLabel={confirmTemplate?.status === "Aktif" ? "Pasifleştir" : "Aktifleştir"}
        onCancel={() => setConfirmTemplate(null)}
        onConfirm={confirmToggleStatus}
      />
      {builderTemplate !== undefined ? <TemplateBuilderModal template={builderTemplate} presets={presets} busy={isSaving} error={actionError} onClose={() => { setBuilderTemplate(undefined); setActionError(""); }} onSave={saveBuilder} /> : null}
    </>
  );
}
