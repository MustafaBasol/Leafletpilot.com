import { useEffect, useState } from "react";
import { canManageTemplates, getSelectedMarketId } from "../api/authSession.js";
import { isRealApiEnabled } from "../api/config.js";
import { outputFormats, templates as mockTemplates } from "../data/mockData.js";
import { getTemplates, updateTemplateStatus } from "../data/dataSource.js";
import { adoptTemplate, createCustomTemplate, getMyTemplates, getSharedTemplates } from "../api/templateApi.js";
import { ConfirmDialog, FilterBar, FilterChip, PageHeader, TemplateCard } from "../components/ui/index.js";

export function Templates() {
  const [items, setItems] = useState(() => (isRealApiEnabled ? [] : mockTemplates));
  const [apiError, setApiError] = useState("");
  const [isLoading, setIsLoading] = useState(isRealApiEnabled);
  const [shared, setShared] = useState([]);
  const [mine, setMine] = useState([]);
  const [actionError, setActionError] = useState("");
  const [confirmTemplate, setConfirmTemplate] = useState(null);
  const selectedMarketId = getSelectedMarketId();
  const canManage = canManageTemplates();

  async function loadTemplates() {
    try {
      setIsLoading(isRealApiEnabled);
      if (isRealApiEnabled) setItems([]);
      const templates = await getTemplates();
      setItems(templates);
      if (isRealApiEnabled) {
        const [sharedResult, mineResult] = await Promise.all([getSharedTemplates(selectedMarketId), getMyTemplates(selectedMarketId)]);
        setShared(sharedResult.items || []);
        setMine(mineResult.items || []);
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

  async function createCustom() {
    try {
      await createCustomTemplate({ name: "Yeni özel şablon", description: "Market tasarımı", template_type: "market", config_json: { slot_count: 8 } }, selectedMarketId);
      setActionError("");
      await loadTemplates();
    } catch (error) { setActionError(error.message || "Özel şablon oluşturulamadı."); }
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
      {isLoading ? <p className="inline-result">Şablonlar yükleniyor...</p> : null}
      {!isLoading && items.length === 0 ? <p className="catalog-empty">Şablon verisi gösterilemiyor.</p> : null}
      {isRealApiEnabled ? (
        <>
          <section className="card" style={{ marginBottom: 24 }}>
            <h2>Paylaşılan şablonlar</h2>
            <p>Planınıza uygun global şablonları marketinize ekleyin.</p>
            <div className="template-management-grid">
              {shared.map((template) => {
                const added = mine.some((item) => item.source_template_id === template.id);
                return <article className="card" key={template.id}><h3>{template.name}</h3><p>{template.description || ""}</p><small>{template.category || "Genel"} · {template.minimum_plan}</small><div><Button onClick={() => addShared(template)} disabled={added}>{added ? "Eklendi" : "Marketime ekle"}</Button></div></article>;
              })}
            </div>
          </section>
          <section className="card" style={{ marginBottom: 24 }}><h2>Özel şablon oluştur</h2><p>Planınız izin veriyorsa marketinize özel bir şablon oluşturabilirsiniz.</p><Button variant="primary" onClick={createCustom}>Özel şablon oluştur</Button></section>
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
    </>
  );
}
