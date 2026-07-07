import { useEffect, useState } from "react";
import { canManageTemplates, getSelectedMarketId } from "../api/authSession.js";
import { isRealApiEnabled } from "../api/config.js";
import { outputFormats, templates as mockTemplates } from "../data/mockData.js";
import { getTemplates, updateTemplateStatus } from "../data/dataSource.js";
import { ConfirmDialog, FilterBar, FilterChip, PageHeader, TemplateCard } from "../components/ui/index.js";

export function Templates() {
  const [items, setItems] = useState(() => (isRealApiEnabled ? [] : mockTemplates));
  const [apiError, setApiError] = useState("");
  const [isLoading, setIsLoading] = useState(isRealApiEnabled);
  const [confirmTemplate, setConfirmTemplate] = useState(null);
  const selectedMarketId = getSelectedMarketId();
  const canManage = canManageTemplates();

  async function loadTemplates() {
    try {
      setIsLoading(isRealApiEnabled);
      if (isRealApiEnabled) setItems([]);
      const templates = await getTemplates();
      setItems(templates);
      setApiError("");
    } catch (error) {
      setItems([]);
      setApiError(error.message || "Şablonlar yüklenemedi.");
    } finally {
      setIsLoading(false);
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
      {isLoading ? <p className="inline-result">Şablonlar yükleniyor...</p> : null}
      {!isLoading && items.length === 0 ? <p className="catalog-empty">Şablon verisi gösterilemiyor.</p> : null}
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
