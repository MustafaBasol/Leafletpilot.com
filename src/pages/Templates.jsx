import { useState } from "react";
import { outputFormats, templates } from "../data/mockData.js";
import { FilterBar, FilterChip, PageHeader, TemplateCard } from "../components/ui/index.js";

export function Templates() {
  const [items, setItems] = useState(templates);

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

  function toggleStatus(id) {
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
