import { useEffect, useMemo, useRef, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { t } from "./platformI18n.js";
import { normalizeOptionalUuid, revokeObjectUrls } from "./platformCatalogUtils.js";
import { PlatformBulkImageImportModal } from "./PlatformBulkImageImportModal.jsx";
import { PlatformProductImportModal } from "./PlatformProductImportModal.jsx";
import { Button } from "../../components/ui/Button.jsx";
import { Modal } from "../../components/ui/Modal.jsx";
import { Table } from "../../components/ui/Table.jsx";

const emptyProduct = { name: "", short_name: "", barcode: "", brand_id: null, category_id: null, package_size: "", package_type: "", aliases: [], is_active: true };
const labels = { categories: "Kategoriler", brands: "Markalar", products: "Ürünler" };
const qualityStatusLabels = { excellent: "Onaylandı", good: "Onaylandı", needs_review: "İnceleme bekliyor", rejected: "Reddedildi", missing: "Görsel yok" };
const qualityStatusBadgeClass = { excellent: "badge-success", good: "badge-success", needs_review: "badge-warning", rejected: "badge-danger", missing: "badge-neutral" };
const resolverEligibleStatuses = new Set(["excellent", "good"]);

function errorText(error) { return error?.body?.detail || error?.message || t("operationFailed"); }
function imageUploadErrorText(error) {
  const detail = errorText(error);
  const messages = {
    "Image content is invalid or corrupt.": "Seçilen dosya geçerli bir PNG/JPEG/WebP görseli değil.",
    "Image content does not match the declared MIME type.": "Seçilen dosyanın içeriği, bildirilen görsel türüyle eşleşmiyor.",
    "Image dimensions are too large.": "Görsel boyutları desteklenen sınırları aşıyor.",
    "Image must be 10 MiB or smaller.": "Görsel en fazla 10 MiB olabilir.",
    "Only PNG, JPEG, and WebP images are allowed.": "Yalnızca PNG, JPEG ve WebP görselleri yüklenebilir.",
  };
  return messages[detail] || detail;
}

export function PlatformCatalog() {
  const [tab, setTab] = useState("products");
  const [rows, setRows] = useState([]);
  const [categories, setCategories] = useState([]);
  const [brands, setBrands] = useState([]);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(emptyProduct);
  const [alias, setAlias] = useState("");
  const [images, setImages] = useState([]);
  const [imageUrls, setImageUrls] = useState({});
  const [preview, setPreview] = useState(null);
  const [file, setFile] = useState(null);
  const [replaceTarget, setReplaceTarget] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [imageBusy, setImageBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [bulkModalOpen, setBulkModalOpen] = useState(false);
  const [productImportOpen, setProductImportOpen] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const imageUrlsRef = useRef({});

  const loadLookups = async () => {
    const [categoryResult, brandResult] = await Promise.all([platformApi.listGlobalCategories({ is_active: true }), platformApi.listGlobalBrands({ is_active: true })]);
    setCategories(categoryResult.items || []); setBrands(brandResult.items || []);
  };
  const load = async () => {
    setLoading(true); setError("");
    try {
      const fn = tab === "categories" ? platformApi.listGlobalCategories : tab === "brands" ? platformApi.listGlobalBrands : platformApi.listGlobalProducts;
      const params = tab === "products" ? { search } : { search };
      setRows((await fn(params)).items || []);
    } catch (err) { setError(errorText(err)); } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [tab]);
  useEffect(() => { loadLookups().catch((err) => setError(errorText(err))); }, []);
  useEffect(() => {
    let disposed = false;
    revokeObjectUrls(imageUrlsRef.current);
    imageUrlsRef.current = {};
    setImageUrls({});
    if (!selected) return undefined;
    Promise.all(images.map(async (image) => [image.id, await platformApi.getGlobalProductImageUrl(selected.id, image.id)]))
      .then((entries) => {
        const nextUrls = Object.fromEntries(entries);
        if (disposed) revokeObjectUrls(nextUrls);
        else { imageUrlsRef.current = nextUrls; setImageUrls(nextUrls); }
      })
      .catch(() => { if (!disposed) setImageUrls({}); });
    return () => { disposed = true; revokeObjectUrls(imageUrlsRef.current); imageUrlsRef.current = {}; };
  }, [selected?.id, images]);

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const openProduct = (product) => {
    setSelected(product); setForm({ ...emptyProduct, ...product, aliases: (product.aliases || []).map((item) => item.alias || item) });
    setImages(product.images || []); setEditorOpen(true); setNotice(""); setError(""); setPreview(null); setFile(null); setReplaceTarget(null);
  };
  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const saveProduct = async (event) => {
    event.preventDefault(); setSaving(true); setError(""); setNotice("");
    if (!form.name.trim()) { setError("Ürün adı zorunludur."); setSaving(false); return; }
    try {
      const body = { ...form, name: form.name.trim(), barcode: form.barcode.trim() || null, brand_id: normalizeOptionalUuid(form.brand_id), category_id: normalizeOptionalUuid(form.category_id), aliases: form.aliases.map((item) => ({ alias: item })) };
      const saved = selected ? await platformApi.updateGlobalProduct(selected.id, body) : await platformApi.createGlobalProduct(body);
      setSelected(saved); setForm({ ...emptyProduct, ...saved, aliases: (saved.aliases || []).map((item) => item.alias || item) });
      setNotice("Ürün kaydedildi."); await load();
    } catch (err) { setError(errorText(err)); } finally { setSaving(false); }
  };
  const addAlias = () => { if (alias.trim() && !form.aliases.includes(alias.trim())) { update("aliases", [...form.aliases, alias.trim()]); setAlias(""); } };
  const chooseFile = (event) => {
    const picked = event.target.files?.[0]; if (!picked) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(picked.type)) { setError("Yalnızca PNG, JPEG ve WebP görselleri yüklenebilir."); return; }
    if (picked.size > 10 * 1024 * 1024) { setError("Görsel en fazla 10 MiB olabilir."); return; }
    setFile(picked); setPreview(URL.createObjectURL(picked)); setError("");
  };
  const uploadImage = async () => {
    if (!selected || !file) return; setImageBusy(true); setError("");
    try { await platformApi.uploadGlobalProductImage(selected.id, file, { mimeType: file.type, primary: replaceTarget?.is_primary || images.length === 0 }); if (replaceTarget) await platformApi.removeGlobalProductImage(selected.id, replaceTarget.id); await refreshProduct(); setReplaceTarget(null); setNotice("Görsel kaydedildi."); setFile(null); setPreview(null); }
    catch (err) { setError(imageUploadErrorText(err)); } finally { setImageBusy(false); }
  };
  const refreshProduct = async () => { const result = await platformApi.listGlobalProducts({ search: selected?.name || "" }); const fresh = (result.items || []).find((item) => item.id === selected?.id); if (fresh) { setSelected(fresh); setImages(fresh.images || []); } await load(); };
  const setPrimary = async (image) => { setImageBusy(true); try { await platformApi.setGlobalProductPrimaryImage(selected.id, image.id); await refreshProduct(); } catch (err) { setError(imageUploadErrorText(err)); } finally { setImageBusy(false); } };
  const removeImage = async (image) => { if (!window.confirm("Bu görsel kaldırılsın mı?")) return; setImageBusy(true); try { await platformApi.removeGlobalProductImage(selected.id, image.id); await refreshProduct(); } catch (err) { setError(imageUploadErrorText(err)); } finally { setImageBusy(false); } };
  const approveImage = async (image) => { setImageBusy(true); setError(""); try { await platformApi.approveGlobalProductImage(selected.id, image.id); setNotice("Görsel onaylandı."); await refreshProduct(); } catch (err) { setError(imageUploadErrorText(err)); } finally { setImageBusy(false); } };
  const rejectImage = async (image) => { setImageBusy(true); setError(""); try { await platformApi.rejectGlobalProductImage(selected.id, image.id); setNotice("Görsel reddedildi."); await refreshProduct(); } catch (err) { setError(imageUploadErrorText(err)); } finally { setImageBusy(false); } };
  const deactivate = async (row) => { try { const fn = tab === "categories" ? platformApi.deactivateGlobalCategory : tab === "brands" ? platformApi.deactivateGlobalBrand : platformApi.deactivateGlobalProduct; await fn(row.id); await load(); } catch (err) { setError(errorText(err)); } };
  const createSimple = async () => { const name = window.prompt(`Yeni ${tab === "categories" ? "kategori" : "marka"} adı`); if (!name?.trim()) return; try { const fn = tab === "categories" ? platformApi.createGlobalCategory : platformApi.createGlobalBrand; await fn({ name: name.trim() }); await load(); } catch (err) { setError(errorText(err)); } };
  const imageUrl = useMemo(() => preview || "", [preview]);

  return <section className="platform-page">
    <div className="platform-catalog-heading"><div><p className="eyebrow">Platform katalog yönetimi</p><h1>Global Katalog</h1><p>Marketlerin kullandığı ortak ürün, marka ve kategori kayıtlarını yönetin.</p></div></div>
    <div className="tabs">{Object.entries(labels).map(([key, label]) => <button type="button" className={tab === key ? "active" : ""} key={key} onClick={() => { setTab(key); setSelected(null); }}>{label}</button>)}</div>
    <div className="catalog-toolbar"><label className="catalog-search"><span>Arama</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("search")} onKeyDown={(event) => event.key === "Enter" && load()} /></label>{tab === "products" && <><label className="catalog-filter"><span>Marka</span><select><option>Tüm markalar</option>{brands.map((brand) => <option key={brand.id}>{brand.name}</option>)}</select></label><label className="catalog-filter"><span>Kategori</span><select><option>Tüm kategoriler</option>{categories.map((category) => <option key={category.id}>{category.name}</option>)}</select></label><label className="catalog-filter"><span>Durum</span><select><option>Tüm durumlar</option><option>Aktif</option><option>Pasif</option></select></label></>}<Button onClick={load}>Ara</Button></div>
    {error && <p className="error-message" role="alert">{error}</p>}{notice && <p className="success-message" role="status">{notice}</p>}
    {tab !== "products" && <div className="page-actions"><Button variant="primary" onClick={createSimple}>{tab === "categories" ? "Kategori ekle" : "Marka ekle"}</Button></div>}
    {tab === "products" && <div className="page-actions"><button type="button" onClick={() => platformApi.downloadGlobalProductImportTemplate()}>Excel Şablonunu İndir</button><button type="button" onClick={() => setProductImportOpen(true)}>Excel ile Ürün Yükle</button><button type="button" onClick={() => setBulkModalOpen(true)}>Toplu Görsel Yükle</button></div>}
    {loading ? <p>Yükleniyor...</p> : rows.length === 0 ? <p className="catalog-empty">Kayıt bulunamadı.</p> : <Table columns={tab === "products" ? ["Görsel", "Ürün", "Marka", "Kategori", "Barkod / SKU", "Paket", "Görsel durumu", "Durum", "Kullanım", "İşlemler"] : ["Ad", "Durum", "Kullanım", "İşlemler"]}>{rows.map((row) => <tr key={row.id}>{tab === "products" && <><td>{row.images?.length ? "Var" : "Yok"}</td><td><strong>{row.name}</strong></td><td>{brands.find((item) => item.id === row.brand_id)?.name || "-"}</td><td>{categories.find((item) => item.id === row.category_id)?.name || "-"}</td><td>{row.barcode || "-"}</td><td>{[row.package_size, row.package_type].filter(Boolean).join(" ") || "-"}</td><td>{row.images?.some((image) => image.quality_status === "needs_review") ? "İnceleme bekliyor" : row.images?.some((image) => resolverEligibleStatuses.has(image.quality_status)) ? "Onaylandı" : row.images?.some((image) => image.quality_status === "rejected") ? "Reddedildi" : "Görsel yok"}</td></>}<td><span className={`badge ${row.is_active ? "badge-success" : "badge-neutral"}`}>{row.is_active ? "Aktif" : "Pasif"}</span></td><td>{row.usage_count ?? 0}</td><td><Button onClick={() => tab === "products" ? openProduct(row) : deactivate(row)}>{tab === "products" ? "Düzenle" : "Pasifleştir"}</Button></td></tr>)}</Table>}
    {tab === "products" && editorOpen && <Modal title={selected ? "Global ürünü düzenle" : "Global ürün ekle"} description="Ürün bilgilerini ve görsel inceleme durumunu bu panelden yönetin." onClose={() => setEditorOpen(false)}><form className="form-grid" onSubmit={saveProduct}>
      <label>Ürün adı<input required value={form.name} onChange={(event) => update("name", event.target.value)} /></label><label>Barkod / SKU<input value={form.barcode || ""} placeholder="Örn. 5449000000996" onChange={(event) => update("barcode", event.target.value)} /></label>
      <label>Marka<select value={form.brand_id || ""} onChange={(event) => update("brand_id", normalizeOptionalUuid(event.target.value))}><option value="">Seçilmedi</option>{brands.map((brand) => <option key={brand.id} value={brand.id}>{brand.name}</option>)}</select></label><label>Kategori<select value={form.category_id || ""} onChange={(event) => update("category_id", normalizeOptionalUuid(event.target.value))}><option value="">Seçilmedi</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
      <label>Paket miktarı<input value={form.package_size || ""} onChange={(event) => update("package_size", event.target.value)} /></label><label>Paket türü<input value={form.package_type || ""} onChange={(event) => update("package_type", event.target.value)} /></label>
      <label>Alternatif adlar<input value={alias} onChange={(event) => setAlias(event.target.value)} onKeyDown={(event) => event.key === "Enter" && (event.preventDefault(), addAlias())} /></label><div>{form.aliases.map((item) => <button type="button" key={item} onClick={() => update("aliases", form.aliases.filter((value) => value !== item))}>{item} ×</button>)}</div>
      <label><input type="checkbox" checked={form.is_active} onChange={(event) => update("is_active", event.target.checked)} /> Aktif</label><button type="submit" disabled={saving}>{saving ? "Kaydediliyor..." : "Ürünü kaydet"}</button>
    </form>
    {selected && <div className="form-grid"><h2>Görseller</h2><input type="file" accept="image/png,image/jpeg,image/webp" onChange={chooseFile} />{replaceTarget && <p>Seçili görsel değiştirilecek.</p>}{imageUrl && <img src={imageUrl} alt="Seçilen görsel önizlemesi" style={{ maxWidth: 180 }} />}<button type="button" disabled={!file || imageBusy} onClick={uploadImage}>{imageBusy ? "Yükleniyor..." : "Görseli yükle"}</button><div>{images.map((image) => <div key={image.id}>{imageUrls[image.id] && <img src={imageUrls[image.id]} alt="Ürün görseli" style={{ maxWidth: 120, maxHeight: 120 }} />}<span>{image.mime_type} · {image.is_primary ? "Birincil" : ""}</span> <span className={`badge ${qualityStatusBadgeClass[image.quality_status] || "badge-neutral"}`} title={resolverEligibleStatuses.has(image.quality_status) ? "Katalogda kullanılabilir" : "Katalogda henüz kullanılamaz"}>{qualityStatusLabels[image.quality_status] || image.quality_status}</span><button type="button" disabled={imageBusy} onClick={() => setReplaceTarget(image)}>Değiştir</button>{image.is_primary ? null : <button type="button" disabled={imageBusy} onClick={() => setPrimary(image)}>Birincil yap</button>}{!resolverEligibleStatuses.has(image.quality_status) && <button type="button" disabled={imageBusy} onClick={() => approveImage(image)}>Onayla</button>}{image.quality_status !== "rejected" && <button type="button" disabled={imageBusy} onClick={() => rejectImage(image)}>Reddet</button>}<button type="button" disabled={imageBusy} onClick={() => removeImage(image)}>Kaldır</button></div>)}</div></div>}
    </Modal>}
    {productImportOpen && <PlatformProductImportModal onClose={() => setProductImportOpen(false)} onImported={load} />}
    {bulkModalOpen && <PlatformBulkImageImportModal onClose={() => setBulkModalOpen(false)} onImported={async () => { await load(); if (selected) await refreshProduct(); }} />}
  </section>;
}
