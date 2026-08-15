import { useEffect, useMemo, useRef, useState } from "react";
import * as catalogApi from "../api/catalogApi.js";
import { isRealApiEnabled } from "../api/config.js";
import { getSelectedMarketId } from "../api/authSession.js";
import { Button, Card, ConfirmDialog, FilterBar, Icon, Modal, PageHeader, ProductThumbnail, StatusBadge, Table } from "../components/ui/index.js";

const emptyForm = {
  private_name: "", private_brand_text: "", private_barcode: "", regular_price: "", promo_price: "", currency: "EUR",
  private_package_size: "", private_package_type: "", package_amount: "", package_unit: "", package_type_canonical: "",
  badge_text: "", stock_note: "", is_active: true,
};
const editFields = [
  ["regular_price", "Normal fiyat", "number"], ["promo_price", "Promosyon fiyatı", "number"],
  ["currency", "Para birimi", "text"], ["private_package_size", "Paket / miktar (örn. 100gr)", "text"],
  ["private_package_type", "Paket türü", "text"], ["badge_text", "Rozet", "text"], ["stock_note", "Stok notu", "text"],
];
const editableProductFields = [
  "regular_price", "promo_price", "currency", "private_brand_text", "private_sku", "private_package_size", "private_package_type",
  "package_amount", "package_unit", "package_type_canonical", "badge_text", "stock_note", "sort_order", "is_active",
];
const identityFields = new Set(["private_name", "private_brand_text", "private_barcode", "private_package_size", "private_package_type", "package_amount", "package_unit", "package_type_canonical"]);
const adoptableMatchTypes = new Set(["exact", "strong"]);

function sourceState(item) {
  if (["global", "local", "global_override"].includes(item.source_state)) return item.source_state;
  if (item.source_type === "Private") return "local";
  if (item.source_type === "Global with tenant override") return "global_override";
  if (item.source_type === "Global") return "global";
  return item.global_product_id ? "global" : "local";
}
function sourceLabel(item) {
  const state = sourceState(item);
  if (state === "global_override") return "Global + Market Düzenlemesi";
  if (state === "global") return "Global Ürün";
  return "Yerel Ürün";
}
function imageLabel(item) {
  if (item.image_override_active) return sourceState(item) === "local" ? "Ürün görseli" : "Market görseli";
  if (item.image_url) return sourceState(item) === "local" ? "Ürün görseli" : "Global görsel";
  return "Görsel yok";
}
function readableError(error) { return error?.message || "İşlem tamamlanamadı. Lütfen tekrar deneyin."; }
function numeric(value) { return value === "" || value == null ? null : Number(value); }
function nullableText(value) { return typeof value === "string" && !value.trim() ? null : value ?? null; }
function packageLabel(item = {}) {
  const structured = item.package_amount != null && item.package_unit ? `${item.package_amount} ${item.package_unit}` : "";
  return [structured || item.package_size, item.package_type].filter(Boolean).join(" ") || "-";
}
function priceLabel(item = {}) {
  const price = item.promo_price ?? item.regular_price;
  return price == null ? "-" : `${price} ${item.currency || ""}`.trim();
}
function matchReasonLabel(reason) {
  const labels = {
    "exact barcode": "Tam barkod eşleşmesi", exact_barcode: "Tam barkod eşleşmesi", barcode: "Tam barkod eşleşmesi",
    "canonical name + brand + package": "Ürün adı + marka + paket eşleşmesi", structured_identity: "Ürün adı + marka + paket eşleşmesi", canonical_name_brand_package: "Ürün adı + marka + paket eşleşmesi",
    "canonical name + package": "Ürün adı + paket eşleşmesi", name_package: "Ürün adı + paket eşleşmesi", canonical_name_package: "Ürün adı + paket eşleşmesi",
    "canonical name + brand": "Ürün adı + marka eşleşmesi", "canonical name": "Ürün adı eşleşmesi",
    "ambiguous candidates": "Birden fazla olası ürün bulundu", ambiguous: "Birden fazla olası ürün bulundu", ambiguous_barcode: "Aynı barkoda sahip birden fazla global ürün bulundu", ambiguous_structured_identity: "Aynı ürün kimliğine sahip birden fazla global ürün bulundu",
    "candidate search truncated": "Aday araması güvenli sınırda durduruldu; otomatik seçim yapılmadı",
    "no global match": "Global katalogda eşleşme bulunamadı", no_match: "Global katalogda eşleşme bulunamadı", barcode_no_match: "Barkodla eşleşen global ürün bulunamadı",
  };
  return labels[reason] || reason || "Deterministik katalog eşleşmesi";
}

const IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);
const IMAGE_SIZE_LIMIT = 10 * 1024 * 1024;

async function validateImageFile(file) {
  if (!file) return;
  if (!IMAGE_TYPES.has(file.type)) throw new Error("PNG, JPEG veya WebP görsel seçin.");
  if (file.size > IMAGE_SIZE_LIMIT) throw new Error("Görsel 10 MB veya daha küçük olmalı.");
  const signature = new Uint8Array(await file.slice(0, 12).arrayBuffer());
  const valid = file.type === "image/png"
    ? signature.slice(0, 8).every((value, index) => value === [137, 80, 78, 71, 13, 10, 26, 10][index])
    : file.type === "image/jpeg"
      ? signature[0] === 255 && signature[1] === 216 && signature[2] === 255
      : String.fromCharCode(...signature.slice(0, 4)) === "RIFF" && String.fromCharCode(...signature.slice(8, 12)) === "WEBP";
  if (!valid) throw new Error("Görsel içeriği seçilen dosya türüyle eşleşmiyor.");
}

function ImagePreview({ file }) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    if (!file) { setSrc(""); return undefined; }
    const url = URL.createObjectURL(file);
    setSrc(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  return src ? <img className="image-preview" src={src} alt="Seçilen ürün görseli önizlemesi" /> : null;
}

function MatchResultPanel({ result, marketId, busyId, onAdopt }) {
  const candidates = result?.candidates || [];
  const canAdopt = adoptableMatchTypes.has(result?.match_type);
  return <section className={`catalog-match-result catalog-match-result--${result?.match_type || "none"}`} aria-live="polite">
    <div className="catalog-match-heading">
      <strong>{result?.match_type === "exact" ? "Tam eşleşme bulundu" : result?.match_type === "strong" ? "Güçlü eşleşme bulundu" : result?.match_type === "ambiguous" ? "Birden fazla olası eşleşme bulundu" : "Global eşleşme bulunamadı"}</strong>
      <small>{result?.match_type === "ambiguous" ? "Belirsiz sonuçlar otomatik olarak kullanılmaz." : matchReasonLabel(result?.match_reason)}</small>
    </div>
    {candidates.map((candidate) => <article className="catalog-match-candidate" key={candidate.product_id}>
      <ProductThumbnail label={candidate.name} hasImage={Boolean(candidate.image_url)} imageUrl={candidate.image_url} marketId={marketId} refreshKey={`match:${candidate.product_id}`} size="sm" />
      <div><strong>{candidate.name}</strong><small>{candidate.brand || "Marka belirtilmedi"} · {packageLabel(candidate)}</small><small>{matchReasonLabel(candidate.match_reason || result.match_reason)}</small></div>
      {candidate.already_adopted ? <span className="catalog-match-existing">Zaten kataloğunuzda</span> : canAdopt ? <Button type="button" variant="primary" disabled={Boolean(busyId)} onClick={() => onAdopt(candidate)}>{busyId === candidate.product_id ? "Ekleniyor..." : "Global ürünü kullan"}</Button> : null}
    </article>)}
    {result?.match_type === "none" ? <small>Ürünü yerel olarak oluşturabilirsiniz.</small> : null}
  </section>;
}

function InheritedSummary({ item }) {
  const inherited = item.inherited_values;
  const effective = item.effective_values || item;
  if (sourceState(item) === "local" || !inherited) return null;
  return <div className="catalog-inherited-summary">
    <strong>Globalden gelen</strong><span>{inherited.name || "-"} · {inherited.brand || "Marka yok"} · {packageLabel(inherited)} · {priceLabel(inherited)}</span>
    <strong>Şu an gösterilen</strong><span>{effective.name || "-"} · {effective.brand || "Marka yok"} · {packageLabel(effective)} · {priceLabel(effective)}</span>
    <small>Aşağıdaki boş alanlar global değeri miras alır; yalnızca markete özel alanları doldurun.</small>
  </div>;
}

function ProductForm({ value, onChange, onSubmit, onCancel, busy, title, nameInput, showImagePicker = false, isGlobalEdit = false, matchResult = null, matching = false, onMatch, onAdopt, marketId, busyId = "", allowLocalContinue = true }) {
  const nameKey = isGlobalEdit ? "display_name_override" : "private_name";
  const matchingEnabled = typeof onMatch === "function";
  return <form className="form-grid" onSubmit={onSubmit}>
    <label className="field field-full"><span>{isGlobalEdit ? "Market ürün adı (isteğe bağlı)" : "Ürün adı *"}</span><input ref={nameInput} required={!isGlobalEdit} value={value[nameKey] ?? ""} onChange={(e) => onChange(nameKey, e.target.value)} placeholder={isGlobalEdit ? "Boşsa global ürün adı kullanılır" : undefined} /></label>
    <label className="field"><span>{isGlobalEdit ? "Market markası (isteğe bağlı)" : "Marka"}</span><input value={value.private_brand_text ?? ""} onChange={(e) => onChange("private_brand_text", e.target.value)} /></label>
    {!isGlobalEdit ? <label className="field"><span>Barkod</span><input inputMode="numeric" value={value.private_barcode ?? ""} onChange={(e) => onChange("private_barcode", e.target.value)} /></label> : null}
    {editFields.map(([key, label, type]) => <label className="field" key={key}><span>{label}</span><input type={type} min={type === "number" ? "0" : undefined} step={type === "number" ? "0.01" : undefined} value={value[key] ?? ""} onChange={(e) => onChange(key, e.target.value)} /></label>)}
    <label className="field"><span>Paket miktarı (yapılandırılmış)</span><input type="number" min="0.001" step="0.001" value={value.package_amount ?? ""} onChange={(e) => onChange("package_amount", e.target.value)} /></label>
    <label className="field"><span>Paket birimi</span><select value={value.package_unit ?? ""} onChange={(e) => onChange("package_unit", e.target.value)}><option value="">Seçin</option>{["g", "kg", "ml", "cl", "l", "pcs"].map((unit) => <option key={unit} value={unit}>{unit}</option>)}</select></label>
    <label className="field field-full"><span>Durum</span><select value={String(value.is_active !== false)} onChange={(e) => onChange("is_active", e.target.value === "true")}><option value="true">Aktif</option><option value="false">Pasif</option></select></label>
    {showImagePicker ? <label className="field field-full image-picker"><span>Ürün görseli (isteğe bağlı)</span><input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => { onChange("imageFile", e.target.files?.[0] || null); e.currentTarget.value = ""; }} disabled={busy} /><small>{value.imageFile ? value.imageFile.name : "PNG, JPEG veya WebP · en fazla 10 MB"}</small>{value.imageFile ? <><ImagePreview file={value.imageFile} /><Button type="button" onClick={() => onChange("imageFile", null)} disabled={busy}>Görseli temizle</Button></> : null}</label> : null}
    {matchResult ? <div className="field-full"><MatchResultPanel result={matchResult} marketId={marketId} busyId={busyId} onAdopt={onAdopt} /></div> : null}
    <div className="field-full page-actions">
      <Button type="button" onClick={onCancel}>İptal</Button>
      {matchingEnabled ? <Button type="button" onClick={onMatch} disabled={busy || matching}>{matching ? "Eşleşme aranıyor..." : "Eşleşme Ara"}</Button> : null}
      {(!matchingEnabled || (matchResult && allowLocalContinue)) ? <Button type="submit" variant="primary" disabled={busy || matching}>{busy ? "Kaydediliyor..." : matchingEnabled ? "Yerel ürün olarak devam et" : title}</Button> : null}
    </div>
  </form>;
}

function marketSettingsPayload(value) {
  return {
    regular_price: numeric(value.regular_price), promo_price: numeric(value.promo_price), currency: value.currency || "EUR",
    badge_text: nullableText(value.badge_text), stock_note: nullableText(value.stock_note), is_active: value.is_active !== false,
  };
}

function privateProductPayload(value, matchType) {
  return {
    ...marketSettingsPayload(value), private_name: value.private_name.trim(), private_brand_text: nullableText(value.private_brand_text),
    private_barcode: nullableText(value.private_barcode), private_package_size: nullableText(value.private_package_size),
    private_package_type: nullableText(value.private_package_type), package_amount: numeric(value.package_amount),
    package_unit: nullableText(value.package_unit), package_type_canonical: nullableText(value.package_type_canonical),
    allow_global_match_override: ["exact", "strong", "ambiguous"].includes(matchType),
  };
}

export function MarketCatalog({ action = "" }) {
  const marketId = getSelectedMarketId();
  const fileInput = useRef(null); const nameInput = useRef(null); const matchRevision = useRef(0); const marketScope = useRef(marketId);
  marketScope.current = marketId;
  const [tab, setTab] = useState("mine"); const [imageRevision, setImageRevision] = useState(0);
  const [query, setQuery] = useState(""); const [source, setSource] = useState("all"); const [active, setActive] = useState("all");
  const [mine, setMine] = useState([]); const [shared, setShared] = useState([]);
  const [form, setForm] = useState(emptyForm); const [editing, setEditing] = useState(null);
  const [matchResult, setMatchResult] = useState(null); const [matching, setMatching] = useState(false);
  const [busy, setBusy] = useState(isRealApiEnabled); const [busyId, setBusyId] = useState("");
  const [error, setError] = useState(""); const [message, setMessage] = useState(""); const [confirm, setConfirm] = useState(null);

  function invalidateMatch() { matchRevision.current += 1; setMatchResult(null); setMatching(false); }
  function resetCreateForm() { invalidateMatch(); setForm(emptyForm); setEditing(null); if (fileInput.current) fileInput.current.value = ""; }
  function openEdit(item) {
    resetCreateForm();
    const overrides = item.override_values || {};
    const local = sourceState(item) === "local";
    setEditing({
      ...item, ...overrides, source_state: sourceState(item), effective_values: { ...item }, imageFile: undefined,
      private_name: local ? (overrides.private_name ?? item.name ?? "") : "",
      display_name_override: local ? "" : (overrides.display_name_override ?? ""),
      private_brand_text: overrides.private_brand_text ?? (local ? item.brand ?? "" : ""),
      private_barcode: overrides.private_barcode ?? "", private_sku: overrides.private_sku ?? "",
      private_package_size: overrides.private_package_size ?? (local ? item.package_size ?? "" : ""),
      private_package_type: overrides.private_package_type ?? (local ? item.package_type ?? "" : ""),
      package_amount: overrides.package_amount ?? "", package_unit: overrides.package_unit ?? "",
      package_type_canonical: overrides.package_type_canonical ?? "",
      regular_price: overrides.regular_price ?? (local ? item.regular_price ?? "" : ""),
      promo_price: overrides.promo_price ?? (local ? item.promo_price ?? "" : ""),
      currency: overrides.currency ?? (local ? item.currency || "EUR" : ""),
      badge_text: overrides.badge_text ?? (local ? item.badge_text ?? "" : ""), stock_note: overrides.stock_note ?? item.stock_note ?? "",
      sort_order: overrides.sort_order ?? item.sort_order ?? 0, is_active: overrides.is_active ?? item.is_active,
    });
  }

  async function loadMine() { if (!isRealApiEnabled) return; const requestedMarketId = marketId; setBusy(true); try { const response = await catalogApi.listMyProducts({ limit: 100 }, requestedMarketId); if (marketScope.current === requestedMarketId) { setMine(response.items || []); setError(""); } } catch (e) { if (marketScope.current === requestedMarketId) setError(readableError(e)); } finally { if (marketScope.current === requestedMarketId) setBusy(false); } }
  async function loadShared() { if (!isRealApiEnabled) return; const requestedMarketId = marketId; setBusy(true); try { const response = await catalogApi.listSharedCatalog({ search: query || undefined, limit: 100 }, requestedMarketId); if (marketScope.current === requestedMarketId) { setShared(response.items || []); setError(""); } } catch (e) { if (marketScope.current === requestedMarketId) setError(readableError(e)); } finally { if (marketScope.current === requestedMarketId) setBusy(false); } }
  useEffect(() => { loadMine(); }, [marketId]);
  useEffect(() => { resetCreateForm(); setMine([]); setShared([]); setConfirm(null); setError(""); setMessage(""); setBusyId(""); }, [marketId]);
  useEffect(() => { if (tab === "shared") loadShared(); }, [tab, marketId]);
  useEffect(() => {
    const activate = () => { resetCreateForm(); setTab("private"); window.setTimeout(() => { nameInput.current?.focus(); nameInput.current?.scrollIntoView({ behavior: "smooth", block: "center" }); }, 0); };
    if (action === "create-private") activate();
    window.addEventListener("leafletpilot:catalog-create", activate);
    return () => window.removeEventListener("leafletpilot:catalog-create", activate);
  }, [action]);

  const visibleMine = useMemo(() => mine.filter((item) => (source === "all" || sourceState(item) === source) && (active === "all" || String(item.is_active) === active) && (!query || [item.name, item.brand, item.category, item.package_size, item.barcode].join(" ").toLocaleLowerCase("tr").includes(query.toLocaleLowerCase("tr")))), [mine, query, source, active]);
  function update(key, value) {
    setForm((current) => {
      const next = { ...current, [key]: value };
      if (key === "private_package_size" && value) { next.package_amount = ""; next.package_unit = ""; }
      if ((key === "package_amount" || key === "package_unit") && value) next.private_package_size = "";
      if (key === "private_package_type") next.package_type_canonical = "";
      return next;
    });
    if (identityFields.has(key)) invalidateMatch();
  }
  function updateEditing(key, value) {
    setEditing((current) => {
      const next = { ...current, [key]: value };
      if (key === "private_package_size" && value) { next.package_amount = ""; next.package_unit = ""; }
      if ((key === "package_amount" || key === "package_unit") && value) next.private_package_size = "";
      if (key === "private_package_type") next.package_type_canonical = "";
      return next;
    });
  }
  async function findMatches(event) {
    if (event?.currentTarget?.form && !event.currentTarget.form.reportValidity()) return;
    if (!form.private_name.trim()) { setError("Eşleşme aramak için ürün adını girin."); nameInput.current?.focus(); return; }
    const revision = ++matchRevision.current;
    setMatching(true); setError(""); setMessage("");
    try {
      const result = await catalogApi.matchGlobalProducts({
        name: form.private_name.trim(), barcode: nullableText(form.private_barcode), brand: nullableText(form.private_brand_text),
        package_size: nullableText(form.private_package_size), package_type: nullableText(form.private_package_type),
        package_amount: numeric(form.package_amount), package_unit: nullableText(form.package_unit),
        package_type_canonical: nullableText(form.package_type_canonical),
      }, marketId);
      if (matchRevision.current === revision) setMatchResult(result);
    } catch (e) { if (matchRevision.current === revision) setError(readableError(e)); }
    finally { if (matchRevision.current === revision) setMatching(false); }
  }
  async function adopt(item) { setBusyId(item.id); setError(""); try { await catalogApi.adoptSharedProduct(item.id, undefined, marketId); setMessage("Ürün kataloğa eklendi."); await Promise.all([loadMine(), loadShared()]); } catch (e) { setError(readableError(e)); } finally { setBusyId(""); } }
  async function adoptMatched(candidate) {
    if (busyId) return;
    setBusyId(candidate.product_id); setError(""); setMessage("");
    try {
      await validateImageFile(form.imageFile);
      const adopted = await catalogApi.adoptSharedProduct(candidate.product_id, { product_id: candidate.product_id, ...marketSettingsPayload(form) }, marketId);
      let completionMessage = "Global ürün kataloğunuza eklendi.";
      if (form.imageFile) {
        try { await catalogApi.uploadProductOverride(adopted.id, form.imageFile, marketId); completionMessage = "Global ürün ve market görseli kataloğunuza eklendi."; }
        catch (imageError) { completionMessage = `Global ürün eklendi ancak görsel yüklenemedi: ${readableError(imageError)} Görseli Düzenle üzerinden yeniden deneyebilirsiniz.`; }
      }
      setMessage(completionMessage); resetCreateForm(); setTab("mine"); await loadMine();
    } catch (e) { setError(readableError(e)); }
    finally { setBusyId(""); }
  }
  async function savePrivate(event) {
    event.preventDefault();
    if (!matchResult) { await findMatches(); return; }
    if (matchResult.candidates?.some((candidate) => candidate.already_adopted)) { setError("Bu global ürün zaten kataloğunuzda; ikinci bir kopya oluşturulamaz."); return; }
    if (busy || busyId) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await validateImageFile(form.imageFile);
      const { imageFile } = form;
      const created = await catalogApi.createPrivateProduct(privateProductPayload(form, matchResult.match_type), marketId);
      if (imageFile) {
        try { await catalogApi.uploadPrivateProductImage(created.id, imageFile, marketId); setMessage("Yerel ürün ve görseli oluşturuldu."); }
        catch (imageError) { setMessage(`Yerel ürün oluşturuldu ancak görsel yüklenemedi: ${readableError(imageError)} Görseli Düzenle üzerinden yeniden deneyebilirsiniz.`); }
      } else setMessage("Yerel ürün oluşturuldu.");
      resetCreateForm(); setTab("mine"); await loadMine();
    } catch (e) { setError(readableError(e)); }
    finally { setBusy(false); }
  }
  async function saveEdit(event) {
    event.preventDefault();
    const local = sourceState(editing) === "local";
    if (local && !editing.private_name?.trim()) { setError("Yerel ürün adı boş bırakılamaz."); return; }
    const fields = [...editableProductFields, local ? "private_name" : "display_name_override", ...(local ? ["private_barcode"] : [])];
    const productFields = Object.fromEntries(fields.flatMap((key) => {
      if (key === "currency" && !editing[key]) return [];
      const value = ["regular_price", "promo_price", "package_amount"].includes(key) ? numeric(editing[key]) : nullableText(editing[key]);
      return [[key, ["is_active", "sort_order"].includes(key) ? editing[key] : value]];
    }));
    setBusyId(editing.id); setError("");
    try { await catalogApi.updateMyProduct(editing.id, productFields, marketId); setEditing(null); setMessage("Ürün değerleri kaydedildi."); await loadMine(); }
    catch (e) { setError(readableError(e)); }
    finally { setBusyId(""); }
  }
  async function toggle(item) { setBusyId(item.id); try { await catalogApi.updateMyProduct(item.id, { is_active: !item.is_active }, marketId); setMessage(item.is_active ? "Ürün pasifleştirildi." : "Ürün aktifleştirildi."); await loadMine(); } catch (e) { setError(readableError(e)); } finally { setBusyId(""); } }
  async function upload(event) { const file = event.target.files?.[0]; const item = editing; if (!file || !item) return; if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) { setError("PNG, JPEG veya WebP görsel seçin."); return; } if (file.size > 10 * 1024 * 1024) { setError("Görsel 10 MB veya daha küçük olmalı."); return; } setBusyId(item.id); try { const updated = await catalogApi.uploadProductOverride(item.id, file, marketId); event.target.value = ""; openEdit(updated); setImageRevision((current) => current + 1); setMessage("Market görseli yüklendi."); await loadMine(); } catch (e) { setError(readableError(e)); } finally { setBusyId(""); } }
  async function removeImage(item) { setBusyId(item.id); try { await catalogApi.removeProductOverride(item.id, marketId); setEditing(null); setImageRevision((current) => current + 1); setMessage(sourceState(item) === "local" ? "Yerel ürün görseli kaldırıldı." : "Market görseli kaldırıldı; uygun global görsel kullanılıyor."); await loadMine(); } catch (e) { setError(readableError(e)); } finally { setBusyId(""); } }

  const adoptedCandidateMatch = Boolean(matchResult?.candidates?.some((candidate) => candidate.already_adopted));
  return <>
    <PageHeader title="Mağaza ürün kataloğu" description="Global ürünleri mağazanıza ekleyin, mağazanıza özel fiyat ve görselleri yönetin." actions={<><Button variant={tab === "mine" ? "primary" : "secondary"} onClick={() => setTab("mine")}>Kataloğum</Button><Button variant={tab === "shared" ? "primary" : "secondary"} onClick={() => setTab("shared")}>Globalden ürün ekle</Button><Button variant="primary" onClick={() => { resetCreateForm(); setTab("private"); window.setTimeout(() => nameInput.current?.focus(), 0); }}>Ürün ekle</Button></>} />
    {error ? <p className="inline-result inline-result-warning" role="alert">{error}</p> : null}{message ? <p className="inline-result" role="status">{message}</p> : null}
    {tab === "private" ? <Card title="Ürün ekle"><ProductForm value={form} onChange={update} onSubmit={savePrivate} onCancel={() => setTab("mine")} busy={busy || Boolean(busyId)} title="Ürünü oluştur" nameInput={nameInput} showImagePicker matchResult={matchResult} matching={matching} onMatch={findMatches} onAdopt={adoptMatched} marketId={marketId} busyId={busyId} allowLocalContinue={!adoptedCandidateMatch} /></Card> : <Card title={tab === "mine" ? "Kataloğum" : "Global katalog"} action={<span className="card-summary">{tab === "mine" ? visibleMine.length : shared.length} ürün</span>}>
      <FilterBar searchPlaceholder="Ürün, marka, kategori veya paket ara" searchValue={query} onSearchChange={(e) => setQuery(e.target.value)}><label className="filter-select"><span>Kaynak</span><select aria-label="Kaynak filtresi" value={source} onChange={(e) => setSource(e.target.value)}><option value="all">Tüm kaynaklar</option><option value="global">Global Ürün</option><option value="local">Yerel Ürün</option><option value="global_override">Global + Market Düzenlemesi</option></select></label><label className="filter-select"><span>Durum</span><select aria-label="Durum filtresi" value={active} onChange={(e) => setActive(e.target.value)}><option value="all">Tüm durumlar</option><option value="true">Aktif</option><option value="false">Pasif</option></select></label><Button onClick={tab === "shared" ? loadShared : loadMine}><Icon name="search" />Ara</Button></FilterBar>
      {busy ? <p className="inline-result">Ürünler yükleniyor...</p> : null}
      <Table columns={["Görsel", "Ürün", "Kaynak", "Fiyat", "Eski fiyat", "Paket", "Durum", "Aksiyonlar"]}>{(tab === "mine" ? visibleMine : shared).map((item) => <tr key={item.id}><td><ProductThumbnail label={item.name} hasImage={Boolean(item.image_url)} imageUrl={item.image_url} marketId={marketId} refreshKey={`${item.id}:${imageRevision}`} size="sm" /><small>{imageLabel(item)}</small></td><td><strong>{item.name}</strong><small>{item.brand || "Marka belirtilmedi"}{item.category ? ` · ${item.category}` : ""}</small></td>{tab === "mine" ? <><td>{sourceLabel(item)}</td><td>{item.promo_price ?? item.regular_price ?? "-"} {item.currency}</td><td>{item.regular_price ?? "-"}</td><td>{packageLabel(item)}</td><td><StatusBadge status={item.is_active ? "Aktif" : "Pasif"} /></td><td><div className="table-actions"><Button onClick={() => openEdit(item)}>Düzenle</Button><Button disabled={busyId === item.id} onClick={() => setConfirm(item)}>{item.is_active ? "Pasifleştir" : "Aktifleştir"}</Button></div></td></> : <><td>Global Ürün</td><td>-</td><td>-</td><td>{packageLabel(item)}</td><td><StatusBadge status={item.is_active ? "Aktif" : "Pasif"} /></td><td><Button variant="primary" disabled={!item.is_active || item.already_added || busyId === item.id} onClick={() => adopt(item)}>{item.already_added ? "Zaten eklendi" : busyId === item.id ? "Ekleniyor..." : "Kataloğa ekle"}</Button></td></>}</tr>)}</Table>{!busy && !(tab === "mine" ? visibleMine : shared).length ? <p className="catalog-empty">Bu filtrelerle eşleşen ürün bulunamadı.</p> : null}
    </Card>}
    {editing ? <Modal title={`${editing.name} ürününü düzenle`} description={sourceState(editing) === "local" ? "Yerel ürün bilgilerini ve market değerlerini düzenleyin." : "Global ürün değişmez; boş market alanları güncel global değerleri kullanır."} onClose={() => setEditing(null)} footer={<><Button onClick={() => setEditing(null)}>İptal</Button><Button variant="primary" onClick={saveEdit} disabled={busyId === editing.id}>{busyId === editing.id ? "Kaydediliyor..." : "Kaydet"}</Button></>}><ProductThumbnail label={editing.name} hasImage={Boolean(editing.image_url)} imageUrl={editing.image_url} marketId={marketId} refreshKey={`${editing.id}:${imageRevision}`} size="lg" /><InheritedSummary item={editing} /><ProductForm value={editing} onChange={updateEditing} onSubmit={saveEdit} onCancel={() => setEditing(null)} busy={busyId === editing.id} title="Kaydet" isGlobalEdit={sourceState(editing) !== "local"} /><div className="page-actions edit-image-actions"><input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={upload} /><Button onClick={() => fileInput.current?.click()} disabled={busyId === editing.id}>{editing.image_override_active ? "Görseli değiştir" : "Market görseli yükle"}</Button>{editing.image_override_active ? <Button variant="danger" onClick={() => setConfirm({ ...editing, removeImage: true })}>Market görselini kaldır</Button> : null}</div></Modal> : null}
    <ConfirmDialog isOpen={Boolean(confirm)} title={confirm?.removeImage ? "Market görselini kaldır" : "Ürün durumunu değiştir"} description={confirm?.removeImage ? "Global görsel varsa kullanılacak; yoksa yer tutucu gösterilecek." : confirm ? `${confirm.name} ürünü ${confirm.is_active ? "pasifleştirilecek" : "aktifleştirilecek"}.` : ""} confirmLabel={confirm?.removeImage ? "Görseli kaldır" : confirm?.is_active ? "Pasifleştir" : "Aktifleştir"} onCancel={() => setConfirm(null)} onConfirm={async () => { const item = confirm; setConfirm(null); if (item.removeImage) await removeImage(item); else await toggle(item); }} isLoading={Boolean(confirm && busyId === confirm.id)} />
  </>;
}
