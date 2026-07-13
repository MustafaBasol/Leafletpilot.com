import { useEffect, useMemo, useRef, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { t } from "./platformI18n.js";
import { normalizeOptionalUuid, revokeObjectUrls } from "./platformCatalogUtils.js";

const emptyProduct = { name: "", short_name: "", barcode: "", brand_id: null, category_id: null, package_size: "", package_type: "", aliases: [], is_active: true };
const labels = { categories: "Categories", brands: "Brands", products: "Products" };

function errorText(error) { return error?.body?.detail || error?.message || t("operationFailed"); }

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
    setImages(product.images || []); setNotice(""); setError(""); setPreview(null); setFile(null); setReplaceTarget(null);
  };
  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const saveProduct = async (event) => {
    event.preventDefault(); setSaving(true); setError(""); setNotice("");
    if (!form.name.trim()) { setError("Product name is required."); setSaving(false); return; }
    try {
      const body = { ...form, name: form.name.trim(), barcode: form.barcode.trim() || null, brand_id: normalizeOptionalUuid(form.brand_id), category_id: normalizeOptionalUuid(form.category_id), aliases: form.aliases.map((item) => ({ alias: item })) };
      const saved = selected ? await platformApi.updateGlobalProduct(selected.id, body) : await platformApi.createGlobalProduct(body);
      setSelected(saved); setForm({ ...emptyProduct, ...saved, aliases: (saved.aliases || []).map((item) => item.alias || item) });
      setNotice("Product saved."); await load();
    } catch (err) { setError(errorText(err)); } finally { setSaving(false); }
  };
  const addAlias = () => { if (alias.trim() && !form.aliases.includes(alias.trim())) { update("aliases", [...form.aliases, alias.trim()]); setAlias(""); } };
  const chooseFile = (event) => {
    const picked = event.target.files?.[0]; if (!picked) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(picked.type)) { setError("Only PNG, JPEG, and WebP images are allowed."); return; }
    if (picked.size > 10 * 1024 * 1024) { setError("Image must be 10 MiB or smaller."); return; }
    setFile(picked); setPreview(URL.createObjectURL(picked)); setError("");
  };
  const uploadImage = async () => {
    if (!selected || !file) return; setImageBusy(true); setError("");
    try { await platformApi.uploadGlobalProductImage(selected.id, file, { mimeType: file.type, primary: replaceTarget?.is_primary || images.length === 0 }); if (replaceTarget) await platformApi.removeGlobalProductImage(selected.id, replaceTarget.id); setReplaceTarget(null); setNotice("Image uploaded."); setFile(null); setPreview(null); await refreshProduct(); }
    catch (err) { setError(errorText(err)); } finally { setImageBusy(false); }
  };
  const refreshProduct = async () => { const result = await platformApi.listGlobalProducts({ search: selected?.name || "" }); const fresh = (result.items || []).find((item) => item.id === selected?.id); if (fresh) { setSelected(fresh); setImages(fresh.images || []); } await load(); };
  const setPrimary = async (image) => { setImageBusy(true); try { await platformApi.setGlobalProductPrimaryImage(selected.id, image.id); await refreshProduct(); } catch (err) { setError(errorText(err)); } finally { setImageBusy(false); } };
  const removeImage = async (image) => { if (!window.confirm("Remove this image?")) return; setImageBusy(true); try { await platformApi.removeGlobalProductImage(selected.id, image.id); await refreshProduct(); } catch (err) { setError(errorText(err)); } finally { setImageBusy(false); } };
  const deactivate = async (row) => { try { const fn = tab === "categories" ? platformApi.deactivateGlobalCategory : tab === "brands" ? platformApi.deactivateGlobalBrand : platformApi.deactivateGlobalProduct; await fn(row.id); await load(); } catch (err) { setError(errorText(err)); } };
  const createSimple = async () => { const name = window.prompt(`New ${tab.slice(0, -1)} name`); if (!name?.trim()) return; try { const fn = tab === "categories" ? platformApi.createGlobalCategory : platformApi.createGlobalBrand; await fn({ name: name.trim() }); await load(); } catch (err) { setError(errorText(err)); } };
  const imageUrl = useMemo(() => preview || "", [preview]);

  return <section className="platform-page">
    <div className="page-header"><h1>Global catalog</h1></div>
    <div className="tabs">{Object.entries(labels).map(([key, label]) => <button type="button" className={tab === key ? "active" : ""} key={key} onClick={() => { setTab(key); setSelected(null); }}>{label}</button>)}</div>
    <div className="toolbar"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("search")} onKeyDown={(event) => event.key === "Enter" && load()} /><button type="button" onClick={load}>{t("search")}</button></div>
    {error && <p className="error-message" role="alert">{error}</p>}{notice && <p className="success-message" role="status">{notice}</p>}
    {tab !== "products" && <button type="button" onClick={createSimple}>Create {tab.slice(0, -1)}</button>}
    {loading ? <p>{t("loading")}</p> : rows.length === 0 ? <p>No records found.</p> : <table><thead><tr><th>Name</th><th>Active</th><th>Usage</th><th /></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td>{row.name}</td><td>{row.is_active ? "Yes" : "No"}</td><td>{row.usage_count ?? 0}</td><td>{tab === "products" ? <button type="button" onClick={() => openProduct(row)}>Edit</button> : row.is_active && <button type="button" onClick={() => deactivate(row)}>Deactivate</button>}</td></tr>)}</tbody></table>}
    {tab === "products" && <form className="form-grid" onSubmit={saveProduct}><h2>{selected ? "Edit global product" : "Create global product"}</h2>
      <label>Canonical name<input required value={form.name} onChange={(event) => update("name", event.target.value)} /></label><label>Barcode / SKU<input value={form.barcode || ""} onChange={(event) => update("barcode", event.target.value)} /></label>
      <label>Brand<select value={form.brand_id || ""} onChange={(event) => update("brand_id", normalizeOptionalUuid(event.target.value))}><option value="">None</option>{brands.map((brand) => <option key={brand.id} value={brand.id}>{brand.name}</option>)}</select></label><label>Category<select value={form.category_id || ""} onChange={(event) => update("category_id", normalizeOptionalUuid(event.target.value))}><option value="">None</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
      <label>Package size<input value={form.package_size || ""} onChange={(event) => update("package_size", event.target.value)} /></label><label>Package type<input value={form.package_type || ""} onChange={(event) => update("package_type", event.target.value)} /></label>
      <label>Aliases<input value={alias} onChange={(event) => setAlias(event.target.value)} onKeyDown={(event) => event.key === "Enter" && (event.preventDefault(), addAlias())} /></label><div>{form.aliases.map((item) => <button type="button" key={item} onClick={() => update("aliases", form.aliases.filter((value) => value !== item))}>{item} ×</button>)}</div>
      <label><input type="checkbox" checked={form.is_active} onChange={(event) => update("is_active", event.target.checked)} /> Active</label><button type="submit" disabled={saving}>{saving ? "Saving..." : "Save product"}</button>
    </form>}
    {tab === "products" && selected && <div className="form-grid"><h2>Images</h2><input type="file" accept="image/png,image/jpeg,image/webp" onChange={chooseFile} />{replaceTarget && <p>Replacing selected image.</p>}{imageUrl && <img src={imageUrl} alt="Selected preview" style={{ maxWidth: 180 }} />}<button type="button" disabled={!file || imageBusy} onClick={uploadImage}>{imageBusy ? "Uploading..." : "Upload image"}</button><div>{images.map((image) => <div key={image.id}>{imageUrls[image.id] && <img src={imageUrls[image.id]} alt="Product" style={{ maxWidth: 120, maxHeight: 120 }} />}<span>{image.mime_type} · {image.is_primary ? "Primary" : ""}</span><button type="button" disabled={imageBusy} onClick={() => setReplaceTarget(image)}>Replace</button>{image.is_primary ? null : <button type="button" disabled={imageBusy} onClick={() => setPrimary(image)}>Make primary</button>}<button type="button" disabled={imageBusy} onClick={() => removeImage(image)}>Remove</button></div>)}</div></div>}
  </section>;
}
