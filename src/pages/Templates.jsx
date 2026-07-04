import { useEffect, useState } from "react";
import { isRealApiEnabled } from "../api/config.js";
import { outputFormats, templates as mockTemplates } from "../data/mockData.js";
import { getTemplates, updateTemplateStatus } from "../data/dataSource.js";
import { FilterBar, FilterChip, PageHeader, TemplateCard } from "../components/ui/index.js";

export function Templates() {
  const [items, setItems] = useState(mockTemplates);
  const [apiError, setApiError] = useState("");
  const [isLoading, setIsLoading] = useState(isRealApiEnabled);

  async function loadTemplates() {
    try {
      setIsLoading(isRealApiEnabled);
      const templates = await getTemplates();
      setItems(templates);
      setApiError("");
    } catch (error) {
      setItems(mockTemplates);
      setApiError(`${error.message || "Şablonlar yüklenemedi."} Mock şablon listesi gösteriliyor.`);
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadTemplates();
  }, []);

  function makeDefault(id) {
    setItems((current) => current.map((template) => ({ ...template, isDefault: template.id === id })));
  }

  function duplicateTemplate(id) {
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

  async function toggleStatus(id) {
    const template = items.find((item) => item.id === id);
    if (!template) return;

    if (isRealApiEnabled) {
      try {
        await updateTemplateStatus(id, template.status !== "Aktif");
        await loadTemplates();
        return;
      } catch (error) {
        setApiError(error.message || "Şablon durumu güncellenemedi.");
        return;
      }
    }

    setItems((current) =>
      current.map((template) =>
        template.id === id ? { ...template, status: template.status === "Aktif" ? "Pasif" : "Aktif", isDefault: false } : template,
      ),
    );
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
      <section className="template-management-grid">
        {items.map((template) => (
          <TemplateCard
            key={template.id}
            template={template}
            onMakeDefault={makeDefault}
            onDuplicate={duplicateTemplate}
            onToggle={toggleStatus}
          />
        ))}
      </section>
    </>
  );
}
