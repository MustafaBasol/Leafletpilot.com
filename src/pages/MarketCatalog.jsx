import { useEffect, useMemo, useRef, useState } from "react";
import * as catalogApi from "../api/catalogApi.js";
import { isRealApiEnabled } from "../api/config.js";
import { getSelectedMarketId } from "../api/authSession.js";
import { Button, Card, ConfirmDialog, FilterBar, Icon, Modal, PageHeader, ProductThumbnail, StatusBadge, Table } from "../components/ui/index.js";

const emptyForm = {
  private_name: "", private_brand_text: "", regular_price: "", promo_price: "", currency: "EUR",
  private_package_size: "", private_package_type: "", badge_text: "", stock_note: "", is_active: true,
};
const editFields = [
  ["regular_price", "Normal fiyat", "number"], ["promo_price", "Promosyon fiyatı", "number"],
  ["currency", "Para birimi", "text"], ["private_package_size", "Paket / miktar", "text"],
  ["private_package_type", "Paket türü", "text"], ["badge_text", "Rozet", "text"], ["stock_note", "Stok notu", "text"],
];
const editableProductFields = ["regular_price", "promo_price", "currency", "private_brand_text", "private_package_size", "private_package_type", "badge_text", "stock_note", "is_active"];

function sourceLabel(item) {
  if (item.source_type === "Global with tenant override") return "Global + mağaza özelleştirmesi";
  if (item.source_type === "Private") return "Özel";
  return item.source_type || (item.product_id ? "Global" : "Özel");
}
function imageLabel(item) { return item.image_override_active ? "Mağaza görseli" : item.image_url ? "Global görsel" : "Görsel yok"; }
function readableError(error) { return error?.message || "İşlem tamamlanamadı. Lütfen tekrar deneyin."; }
function numeric(value) { return value === "" ? null : Number(value); }

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

function ProductForm({ value, onChange, onSubmit, onCancel, busy, title, nameInput, showImagePicker = false }) {
  return <form className="form-grid" onSubmit={onSubmit}>
    <label className="field field-full"><span>Ürün adı *</span><input ref={nameInput} required value={value.private_name || value.name || ""} onChange={(e) => onChange("private_name", e.target.value)} /></label>
    <label className="field"><span>Marka</span><input value={value.private_brand_text || ""} onChange={(e) => onChange("private_brand_text", e.target.value)} /></label>
    {editFields.map(([key, label, type]) => <label className="field" key={key}><span>{label}</span><input type={type} step={type === "number" ? "0.01" : undefined} value={value[key] ?? ""} onChange={(e) => onChange(key, e.target.value)} /></label>)}
    <label className="field field-full"><span>Durum</span><select value={String(value.is_active !== false)} onChange={(e) => onChange("is_active", e.target.value === "true")}><option value="true">Aktif</option><option value="false">Pasif</option></select></label>
    {showImagePicker ? <label className="field field-full image-picker"><span>Ürün görseli (isteğe bağlı)</span><input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => { onChange("imageFile", e.target.files?.[0] || null); e.currentTarget.value = ""; }} disabled={busy} /><small>{value.imageFile ? value.imageFile.name : "PNG, JPEG veya WebP · en fazla 10 MB"}</small>{value.imageFile ? <><ImagePreview file={value.imageFile} /><Button type="button" onClick={() => onChange("imageFile", null)} disabled={busy}>Görseli temizle</Button></> : null}</label> : null}
    <div className="field-full page-actions"><Button type="button" onClick={onCancel}>İptal</Button><Button type="submit" variant="primary" disabled={busy}>{busy ? "Kaydediliyor..." : title}</Button></div>
  </form>;
}

export function MarketCatalog({ action = "" }) {
  const marketId = getSelectedMarketId();
  const fileInput = useRef(null);
  const nameInput = useRef(null);
  const [tab, setTab] = useState("mine");
  const [imageRevision, setImageRevision] = useState(0);
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("all");
  const [active, setActive] = useState("all");
  const [mine, setMine] = useState([]); const [shared, setShared] = useState([]);
  const [form, setForm] = useState(emptyForm); const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(isRealApiEnabled); const [busyId, setBusyId] = useState("");
  const [error, setError] = useState(""); const [message, setMessage] = useState(""); const [confirm, setConfirm] = useState(null);

  function resetCreateForm() { setForm(emptyForm); setEditing(null); if (fileInput.current) fileInput.current.value = ""; }
  function openEdit(item) { resetCreateForm(); setEditing({ ...item, imageFile: undefined }); }

  async function loadMine() { if (!isRealApiEnabled) return; setBusy(true); try { const response = await catalogApi.listMyProducts({ limit: 100 }, marketId); setMine(response.items || []); setError(""); } catch (e) { setError(readableError(e)); } finally { setBusy(false); } }
  async function loadShared() { if (!isRealApiEnabled) return; setBusy(true); try { const response = await catalogApi.listSharedCatalog({ search: query || undefined, limit: 100 }, marketId); setShared(response.items || []); setError(""); } catch (e) { setError(readableError(e)); } finally { setBusy(false); } }
  useEffect(() => { loadMine(); }, [marketId]);
  useEffect(() => { if (tab === "shared") loadShared(); }, [tab]);
  useEffect(() => {
    const activate = () => { resetCreateForm(); setTab("private"); window.setTimeout(() => { nameInput.current?.focus(); nameInput.current?.scrollIntoView({ behavior: "smooth", block: "center" }); }, 0); };
    if (action === "create-private") activate();
    window.addEventListener("leafletpilot:catalog-create", activate);
    return () => window.removeEventListener("leafletpilot:catalog-create", activate);
  }, [action]);

  const visibleMine = useMemo(() => mine.filter((item) => (source === "all" || (source === "private" ? !item.product_id : item.product_id)) && (active === "all" || String(item.is_active) === active) && (!query || [item.name, item.brand, item.category, item.package_size].join(" ").toLocaleLowerCase("tr").includes(query.toLocaleLowerCase("tr")))), [mine, query, source, active]);
  function update(key, value) { setForm((current) => ({ ...current, [key]: value })); }
  async function adopt(item) { setBusyId(item.id); setError(""); try { await catalogApi.adoptSharedProduct(item.id, undefined, marketId); setMessage("Ürün kataloğa eklendi."); await Promise.all([loadMine(), loadShared()]); } catch (e) { setError(readableError(e)); } finally { setBusyId(""); } }
  async function savePrivate(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError("");
    try {
      await validateImageFile(form.imageFile);
      const { imageFile, ...payload } = form;
      const created = await catalogApi.createPrivateProduct({ ...payload, regular_price: numeric(form.regular_price), promo_price: numeric(form.promo_price) }, marketId);
      if (imageFile) {
        try {
          await catalogApi.uploadPrivateProductImage(created.id, imageFile, marketId);
          setMessage("Özel ürün ve görseli oluşturuldu.");
        } catch (imageError) {
          setMessage(`Özel ürün oluşturuldu ancak görsel yüklenemedi: ${readableError(imageError)} Görseli Düzenle üzerinden yeniden deneyebilirsiniz.`);
        }
      } else setMessage("Özel ürün oluşturuldu.");
      setForm(emptyForm); setTab("mine"); await loadMine();
    } catch (e) { setError(readableError(e)); }
    finally { setBusy(false); }
  }
  async function saveEdit(event) { event.preventDefault(); const productFields = Object.fromEntries(editableProductFields.map((key) => [key, editing[key]])); setBusyId(editing.id); setError(""); try { await catalogApi.updateMyProduct(editing.id, { ...productFields, regular_price: numeric(editing.regular_price), promo_price: numeric(editing.promo_price) }, marketId); setEditing(null); setMessage("Ürün değerleri kaydedildi."); await loadMine(); } catch (e) { setError(readableError(e)); } finally { setBusyId(""); } }
  async function toggle(item) { setBusyId(item.id); try { await catalogApi.updateMyProduct(item.id, { is_active: !item.is_active }, marketId); setMessage(item.is_active ? "Ürün pasifleştirildi." : "Ürün aktifleştirildi."); await loadMine(); } catch (e) { setError(readableError(e)); } finally { setBusyId(""); } }
  async function upload(event) { const file = event.target.files?.[0]; const item = editing; if (!file || !item) return; if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) { setError("PNG, JPEG veya WebP görsel seçin."); return; } if (file.size > 10 * 1024 * 1024) { setError("Görsel 10 MB veya daha küçük olmalı."); return; } setBusyId(item.id); try { const updated = await catalogApi.uploadProductOverride(item.id, file, marketId); event.target.value = ""; setEditing(updated); setImageRevision((current) => current + 1); setMessage("Mağaza görseli yüklendi."); await loadMine(); } catch (e) { setError(readableError(e)); } finally { setBusyId(""); } }
  async function removeImage(item) { setBusyId(item.id); try { await catalogApi.removeProductOverride(item.id, marketId); setEditing(null); setImageRevision((current) => current + 1); setMessage("Mağaza görseli kaldırıldı; uygun global görsel kullanılıyor."); await loadMine(); } catch (e) { setError(readableError(e)); } finally { setBusyId(""); } }

  return <>
    <PageHeader title="Mağaza ürün kataloğu" description="Global ürünleri mağazanıza ekleyin, mağazanıza özel fiyat ve görselleri yönetin." actions={<><Button variant={tab === "mine" ? "primary" : "secondary"} onClick={() => setTab("mine")}>Kataloğum</Button><Button variant={tab === "shared" ? "primary" : "secondary"} onClick={() => setTab("shared")}>Globalden ürün ekle</Button><Button variant="primary" onClick={() => { resetCreateForm(); setTab("private"); window.setTimeout(() => nameInput.current?.focus(), 0); }}>Özel ürün oluştur</Button></>} />
    {error ? <p className="inline-result inline-result-warning" role="alert">{error}</p> : null}{message ? <p className="inline-result" role="status">{message}</p> : null}
    {tab === "private" ? <Card title="Özel ürün oluştur"><ProductForm value={form} onChange={update} onSubmit={savePrivate} onCancel={() => setTab("mine")} busy={busy} title="Ürünü oluştur" nameInput={nameInput} showImagePicker /></Card> : <Card title={tab === "mine" ? "Kataloğum" : "Global katalog"} action={<span className="card-summary">{tab === "mine" ? visibleMine.length : shared.length} ürün</span>}>
      <FilterBar searchPlaceholder="Ürün, marka, kategori veya paket ara" searchValue={query} onSearchChange={(e) => setQuery(e.target.value)}><label className="filter-select"><span>Kaynak</span><select aria-label="Kaynak filtresi" value={source} onChange={(e) => setSource(e.target.value)}><option value="all">Tüm kaynaklar</option><option value="global">Global</option><option value="private">Özel</option></select></label><label className="filter-select"><span>Durum</span><select aria-label="Durum filtresi" value={active} onChange={(e) => setActive(e.target.value)}><option value="all">Tüm durumlar</option><option value="true">Aktif</option><option value="false">Pasif</option></select></label><Button onClick={tab === "shared" ? loadShared : loadMine}><Icon name="search" />Ara</Button></FilterBar>
      {busy ? <p className="inline-result">Ürünler yükleniyor...</p> : null}
      <Table columns={["Görsel", "Ürün", "Kaynak", "Fiyat", "Eski fiyat", "Paket", "Durum", "Aksiyonlar"]}>{(tab === "mine" ? visibleMine : shared).map((item) => <tr key={item.id}><td><ProductThumbnail label={item.name} hasImage={Boolean(item.image_url)} imageUrl={item.image_url} marketId={marketId} refreshKey={`${item.id}:${imageRevision}`} size="sm" /><small>{imageLabel(item)}</small></td><td><strong>{item.name}</strong><small>{item.brand || "Marka belirtilmedi"}{item.category ? ` · ${item.category}` : ""}</small></td>{tab === "mine" ? <><td>{sourceLabel(item)}</td><td>{item.promo_price ?? item.regular_price ?? "-"} {item.currency}</td><td>{item.regular_price ?? "-"}</td><td>{[item.package_size, item.package_type].filter(Boolean).join(" · ") || "-"}</td><td><StatusBadge status={item.is_active ? "Aktif" : "Pasif"} /></td><td><div className="table-actions"><Button onClick={() => openEdit(item)}>Düzenle</Button><Button disabled={busyId === item.id} onClick={() => setConfirm(item)}>{item.is_active ? "Pasifleştir" : "Aktifleştir"}</Button></div></td></> : <><td>Global</td><td>-</td><td>-</td><td>{[item.package_size, item.package_type].filter(Boolean).join(" · ") || "-"}</td><td><StatusBadge status={item.is_active ? "Aktif" : "Pasif"} /></td><td><Button variant="primary" disabled={!item.is_active || item.already_added || busyId === item.id} onClick={() => adopt(item)}>{item.already_added ? "Zaten eklendi" : busyId === item.id ? "Ekleniyor..." : "Kataloğa ekle"}</Button></td></>}</tr>)}</Table>{!busy && !(tab === "mine" ? visibleMine : shared).length ? <p className="catalog-empty">Bu filtrelerle eşleşen ürün bulunamadı.</p> : null}
    </Card>}
    {editing ? <Modal title={`${editing.name} ürününü düzenle`} description="Global ürün değişmez; burada yalnızca mağazanıza özel değerler tutulur." onClose={() => setEditing(null)} footer={<><Button onClick={() => setEditing(null)}>İptal</Button><Button variant="primary" onClick={saveEdit} disabled={busyId === editing.id}>{busyId === editing.id ? "Kaydediliyor..." : "Kaydet"}</Button></>}><ProductThumbnail label={editing.name} hasImage={Boolean(editing.image_url)} imageUrl={editing.image_url} marketId={marketId} refreshKey={`${editing.id}:${imageRevision}`} size="lg" /><ProductForm value={editing} onChange={(key, value) => setEditing((current) => ({ ...current, [key]: value }))} onSubmit={saveEdit} onCancel={() => setEditing(null)} busy={busyId === editing.id} title="Kaydet" /><div className="page-actions edit-image-actions"><input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={upload} /><Button onClick={() => fileInput.current?.click()} disabled={busyId === editing.id}>{editing.image_override_active ? "Görseli değiştir" : "Mağaza görseli yükle"}</Button>{editing.image_override_active ? <Button variant="danger" onClick={() => setConfirm({ ...editing, removeImage: true })}>Mağaza görselini kaldır</Button> : null}</div></Modal> : null}
    <ConfirmDialog isOpen={Boolean(confirm)} title={confirm?.removeImage ? "Mağaza görselini kaldır" : "Ürün durumunu değiştir"} description={confirm?.removeImage ? "Global görsel varsa kullanılacak; yoksa yer tutucu gösterilecek." : confirm ? `${confirm.name} ürünü ${confirm.is_active ? "pasifleştirilecek" : "aktifleştirilecek"}.` : ""} confirmLabel={confirm?.removeImage ? "Görseli kaldır" : confirm?.is_active ? "Pasifleştir" : "Aktifleştir"} onCancel={() => setConfirm(null)} onConfirm={async () => { const item = confirm; setConfirm(null); if (item.removeImage) await removeImage(item); else await toggle(item); }} isLoading={Boolean(confirm && busyId === confirm.id)} />
  </>;
}
