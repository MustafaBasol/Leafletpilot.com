import { useEffect, useRef, useState } from "react";
import { canManageTemplates, getSelectedMarketId } from "../api/authSession.js";
import { isRealApiEnabled } from "../api/config.js";
import { outputFormats, templates as mockTemplates } from "../data/mockData.js";
import { getBillingSubscription, getTemplates, updateTemplateStatus } from "../data/dataSource.js";
import { adoptTemplate, createCustomTemplate, getMyTemplates, getSharedTemplates, getTemplatePresets, updateTemplate, uploadTemplateThumbnail } from "../api/templateApi.js";
import { Badge, Button, ConfirmDialog, FilterBar, FilterChip, PageHeader, TemplateCard, TemplateThumbnail } from "../components/ui/index.js";
import { TemplateBuilderModal } from "../components/templates/TemplateBuilderModal.jsx";

// Mirrors backend/app/services/plans.py's CANONICAL_PLAN_CODES/PLAN_RANK — the
// display-name + rank convention already established in Billing.jsx.
const PLAN_LABELS = { starter: "Başlangıç", standard: "Plus", pro: "Pro" };
const PLAN_ORDER = ["starter", "standard", "pro"];
const PLAN_BADGE_TONE = { standard: "primary", pro: "warning" };

function planRankOf(code) {
  const index = PLAN_ORDER.indexOf(code);
  return index === -1 ? 0 : index;
}

const fallbackPresets = {
  items: [
    { slug: "promo-4", name: "Promo 4", columns: 2, rows: 2 },
    { slug: "supermarket-promo-4", name: "Supermarket Promo 4", columns: 2, rows: 2 },
    { slug: "supermarket-promo-9", name: "Supermarket Promo 9", columns: 3, rows: 3 },
    { slug: "supermarket-promo-16", name: "Supermarket Promo 16", columns: 4, rows: 4 },
  ],
  page_formats: [{ value: "a4_portrait", label: "A4 dikey" }],
  price_styles: ["bold", "panel", "ticket", "split"], badge_styles: ["pill", "sticker", "burst", "ribbon"],
  header_styles: ["burst", "band", "minimal"], card_styles: ["shadow", "outlined", "rounded"],
  image_treatments: ["stage", "cutout", "photo"],
};

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
  const [planCode, setPlanCode] = useState("");
  const [addingId, setAddingId] = useState("");
  const submittingRef = useRef(false);
  const selectedMarketId = getSelectedMarketId();
  const canManage = canManageTemplates();
  const currentPlanRank = planRankOf(planCode);

  async function loadTemplates() {
    try {
      setIsLoading(isRealApiEnabled);
      if (isRealApiEnabled) setItems([]);
      const templates = await getTemplates();
      setItems(templates);
      if (isRealApiEnabled) {
        const [sharedResult, mineResult, presetResult, subscription] = await Promise.all([
          getSharedTemplates(selectedMarketId),
          getMyTemplates(selectedMarketId),
          getTemplatePresets(selectedMarketId),
          getBillingSubscription(),
        ]);
        setShared(sharedResult.items || []);
        setMine(mineResult.items || []);
        setPresets(presetResult);
        setPlanCode(subscription?.plan_code || "starter");
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
    if (addingId) return;
    setAddingId(template.id);
    try {
      await adoptTemplate(template.id, selectedMarketId);
      setActionError("");
      setSuccess(`${template.name} şablonu marketinize eklendi.`);
      await loadTemplates();
    } catch (error) {
      if (error.status === 409) setActionError("Bu şablon zaten markete eklenmiş.");
      else if (error.status === 403) setActionError("Bu şablonu eklemek için planınızı yükseltmeniz gerekiyor.");
      else setActionError(error.message || "Şablon eklenemedi.");
    } finally {
      setAddingId("");
    }
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
      setSuccess(`${saved.name} şablonu ${builderTemplate ? "güncellendi" : "kaydedildi"}.`);
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
                const minimumPlan = template.minimum_plan || "starter";
                const locked = planRankOf(minimumPlan) > currentPlanRank;
                return (
                  <article className="card template-real-card" key={template.id}>
                    <a className="template-thumb-link" href={`#/templates/${template.id}`}>
                      <TemplateThumbnail
                        templateId={template.id}
                        thumbnailKey={template.thumbnail_key}
                        marketId={selectedMarketId}
                        previewTone={template.config_json?.preview_tone || "classic"}
                        name={template.name}
                        type={template.template_type}
                      />
                    </a>
                    <span className="template-source">Global</span>
                    {minimumPlan !== "starter" ? <Badge tone={PLAN_BADGE_TONE[minimumPlan] || "primary"}>{PLAN_LABELS[minimumPlan] || minimumPlan}</Badge> : null}
                    <h3>{template.name}</h3>
                    <p>{template.description || ""}</p>
                    <small>{template.config_json?.page_format === "a4_landscape" ? "A4 yatay" : "A4 dikey"} · {template.config_json?.slot_count || "-"} ürün</small>
                    <div className="table-actions">
                      <Button href={`#/templates/${template.id}`}>Önizle</Button>
                      {locked ? null : (
                        <Button variant="primary" onClick={() => addShared(template)} disabled={added || addingId === template.id}>
                          {added ? "Eklendi" : addingId === template.id ? "Ekleniyor..." : "Marketime ekle"}
                        </Button>
                      )}
                    </div>
                    {locked ? (
                      <div className="template-lock">
                        <p className="template-lock-note">Bu şablon {PLAN_LABELS[minimumPlan] || minimumPlan} planına dahildir.</p>
                        <Button href="#/settings/billing">Planı Yükselt</Button>
                      </div>
                    ) : null}
                  </article>
                );
              })}
            </div>
          </section>
          <section className="card" style={{ marginBottom: 24 }}><h2>Özel şablon oluştur</h2><p>Planınız izin veriyorsa marketinize özel bir şablon oluşturabilirsiniz.</p><Button variant="primary" disabled={!canManage} onClick={() => { setActionError(""); setBuilderTemplate(null); }}>Özel şablon oluştur</Button></section>
          <section className="card" style={{ marginBottom: 24 }}><h2>Marketimin şablonları</h2><div className="template-management-grid">{mine.map((template) => <article className="card template-real-card" key={template.id}><a className="template-thumb-link" href={`#/templates/${template.id}`}><TemplateThumbnail templateId={template.id} thumbnailKey={template.thumbnail_key} marketId={selectedMarketId} previewTone={template.config_json?.preview_tone || "classic"} name={template.name} type={template.template_type} /></a><span className="template-source">{template.source_template_id ? "Globalden kopyalandı" : "Markete özel"}</span><h3>{template.name}</h3><p>{template.description || ""}</p><small>{template.config_json?.page_format === "a4_landscape" ? "A4 yatay" : "A4 dikey"} · {template.config_json?.slot_count || "-"} ürün · {template.is_active ? "Aktif" : "Pasif"}</small><div className="table-actions"><Button href={`#/templates/${template.id}`}>Önizle</Button>{canManage ? <><Button variant="primary" onClick={() => { setActionError(""); setBuilderTemplate(template); }}>Düzenle</Button><Button onClick={async () => { await updateTemplate(template.id, { is_active: !template.is_active }, selectedMarketId); await loadTemplates(); }}>{template.is_active ? "Pasifleştir" : "Aktifleştir"}</Button></> : null}</div></article>)}</div></section>
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
