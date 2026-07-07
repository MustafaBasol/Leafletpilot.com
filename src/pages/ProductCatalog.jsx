import { useEffect, useMemo, useState } from "react";
import { canMutateCatalog, getSelectedMarketId } from "../api/authSession.js";
import { isRealApiEnabled } from "../api/config.js";
import { products as initialProducts } from "../data/mockData.js";
import {
  createCatalogProduct,
  getProductCatalogData,
  updateCatalogProduct,
  updateCatalogProductStatus,
} from "../data/dataSource.js";
import { Button, Card, ConfirmDialog, FilterBar, Modal, PageHeader, ProductThumbnail, StatusBadge, Table } from "../components/ui/index.js";

const emptyProduct = {
  name: "",
  shortName: "",
  brandId: "",
  categoryId: "",
  barcode: "",
  packageSize: "",
  packageType: "",
  alternativeNamesText: "",
  status: "Aktif",
};

const allFilters = {
  brandId: "all",
  categoryId: "all",
  imageStatus: "all",
  status: "all",
};

function normalizeSearch(value) {
  return String(value || "").toLocaleLowerCase("tr-TR");
}

function FilterSelect({ label, value, onChange, options }) {
  return (
    <label className="filter-select">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} aria-label={label}>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </select>
    </label>
  );
}

function Field({ label, children }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function ProductFormModal({ product, brands, categories, onClose, onSave, isSaving, error }) {
  const [form, setForm] = useState(() => ({
    ...emptyProduct,
    ...product,
    alternativeNamesText: (product?.alternativeNames || []).join(", "),
  }));

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function submit(event) {
    event.preventDefault();
    onSave(form);
  }

  return (
    <Modal
      title={product ? "Ürünü Düzenle" : "Ürün Ekle"}
      description="Market kataloğundaki ürün bilgilerini güncelleyin."
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Vazgeç</Button>
          <Button variant="primary" type="submit" form="product-form" disabled={isSaving}>
            {isSaving ? "Kaydediliyor..." : "Kaydet"}
          </Button>
        </>
      }
    >
      <form id="product-form" className="form-grid" onSubmit={submit}>
        <Field label="Ürün adı">
          <input value={form.name} onChange={(event) => update("name", event.target.value)} required />
        </Field>
        <Field label="Kısa ad">
          <input value={form.shortName || ""} onChange={(event) => update("shortName", event.target.value)} />
        </Field>
        <Field label="Barkod">
          <input value={form.barcode || ""} onChange={(event) => update("barcode", event.target.value)} />
        </Field>
        <Field label="Marka">
          <select value={form.brandId || ""} onChange={(event) => update("brandId", event.target.value)}>
            <option value="">Seçilmedi</option>
            {brands.map((brand) => (
              <option value={brand.id} key={brand.id}>{brand.name}</option>
            ))}
          </select>
        </Field>
        <Field label="Kategori">
          <select value={form.categoryId || ""} onChange={(event) => update("categoryId", event.target.value)}>
            <option value="">Seçilmedi</option>
            {categories.map((category) => (
              <option value={category.id} key={category.id}>{category.name}</option>
            ))}
          </select>
        </Field>
        <Field label="Durum">
          <select value={form.status || "Aktif"} onChange={(event) => update("status", event.target.value)}>
            <option value="Aktif">Aktif</option>
            <option value="Pasif">Pasif</option>
          </select>
        </Field>
        <Field label="Paket boyutu">
          <input value={form.packageSize || ""} onChange={(event) => update("packageSize", event.target.value)} />
        </Field>
        <Field label="Paket tipi">
          <input value={form.packageType || ""} onChange={(event) => update("packageType", event.target.value)} />
        </Field>
        <Field label="Alternatif isimler">
          <input value={form.alternativeNamesText || ""} onChange={(event) => update("alternativeNamesText", event.target.value)} />
        </Field>
        {error ? <p className="form-error field-full">{error}</p> : null}
      </form>
    </Modal>
  );
}

export function ProductCatalog() {
  const [products, setProducts] = useState(() =>
    initialProducts.map((product) => ({ ...product, brandId: product.brand, categoryId: product.category })),
  );
  const [brands, setBrands] = useState([]);
  const [categories, setCategories] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [filters, setFilters] = useState(allFilters);
  const [editingProduct, setEditingProduct] = useState(null);
  const [isAdding, setIsAdding] = useState(false);
  const [isLoading, setIsLoading] = useState(isRealApiEnabled);
  const [isSaving, setIsSaving] = useState(false);
  const [isTogglingId, setIsTogglingId] = useState("");
  const [confirmProduct, setConfirmProduct] = useState(null);
  const [apiError, setApiError] = useState("");
  const [modalError, setModalError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const selectedMarketId = getSelectedMarketId();
  const canEditCatalog = canMutateCatalog();

  async function loadCatalog() {
    if (!isRealApiEnabled) return;

    try {
      setIsLoading(true);
      setProducts([]);
      setBrands([]);
      setCategories([]);
      const catalogData = await getProductCatalogData();
      setProducts(catalogData.products);
      setBrands(catalogData.brands);
      setCategories(catalogData.categories);
      setApiError("");
    } catch (error) {
      setProducts([]);
      setBrands([]);
      setCategories([]);
      setApiError(`${error.message} Ürün kataloğu şu anda yüklenemiyor.`);
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadCatalog();
  }, [selectedMarketId]);

  const fallbackBrands = useMemo(() => {
    const names = Array.from(new Set(products.map((product) => product.brand).filter(Boolean)));
    return names.map((name) => ({ id: name, name }));
  }, [products]);

  const fallbackCategories = useMemo(() => {
    const names = Array.from(new Set(products.map((product) => product.category).filter(Boolean)));
    return names.map((name) => ({ id: name, name }));
  }, [products]);

  const brandOptions = brands.length ? brands : fallbackBrands;
  const categoryOptions = categories.length ? categories : fallbackCategories;

  const filteredProducts = useMemo(() => {
    const query = normalizeSearch(searchTerm);

    return products.filter((product) => {
      const searchable = [
        product.name,
        product.barcode,
        product.brand,
        product.category,
        ...(product.alternativeNames || []),
      ]
        .map(normalizeSearch)
        .join(" ");

      const matchesSearch = !query || searchable.includes(query);
      const matchesBrand = filters.brandId === "all" || product.brandId === filters.brandId || product.brand === filters.brandId;
      const matchesCategory =
        filters.categoryId === "all" || product.categoryId === filters.categoryId || product.category === filters.categoryId;
      const matchesImage =
        filters.imageStatus === "all" ||
        (filters.imageStatus === "with" && product.imageStatus !== "Görsel yok") ||
        (filters.imageStatus === "without" && product.imageStatus === "Görsel yok");
      const matchesStatus = filters.status === "all" || product.status === filters.status;

      return matchesSearch && matchesBrand && matchesCategory && matchesImage && matchesStatus;
    });
  }, [filters, products, searchTerm]);

  function updateFilter(field, value) {
    setFilters((current) => ({ ...current, [field]: value }));
  }

  function closeModal() {
    setEditingProduct(null);
    setIsAdding(false);
    setModalError("");
  }

  async function saveProduct(form) {
    if (isRealApiEnabled) {
      try {
        setIsSaving(true);
        setModalError("");
        if (form.id) {
          await updateCatalogProduct(form.id, form);
          setSuccessMessage("Ürün kaydedildi.");
        } else {
          await createCatalogProduct(form);
          setSuccessMessage("Ürün eklendi.");
        }
        closeModal();
        await loadCatalog();
      } catch (error) {
        setModalError(error.message || "Ürün kaydedilemedi.");
      } finally {
        setIsSaving(false);
      }
      return;
    }

    const nextProduct = {
      ...form,
      id: form.id || `product-${Date.now()}`,
      brandId: form.brandId || form.brand,
      categoryId: form.categoryId || form.category,
      alternativeNames: form.alternativeNamesText
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      imageStatus: form.imageStatus || "Görsel yok",
      usageCount: form.usageCount || 0,
    };

    setProducts((current) =>
      form.id ? current.map((item) => (item.id === form.id ? nextProduct : item)) : [nextProduct, ...current],
    );
    closeModal();
  }

  async function toggleProductStatus(product) {
    const nextStatus = product.status === "Aktif" ? "Pasif" : "Aktif";

    if (isRealApiEnabled) {
      try {
        setIsTogglingId(product.id);
        setApiError("");
        await updateCatalogProductStatus(product.id, nextStatus === "Aktif");
        setSuccessMessage(nextStatus === "Aktif" ? "Ürün aktifleştirildi." : "Ürün pasifleştirildi.");
        await loadCatalog();
      } catch (error) {
        setApiError(error.message || "Ürün durumu güncellenemedi.");
      } finally {
        setIsTogglingId("");
      }
      return;
    }

    setProducts((current) => current.map((item) => (item.id === product.id ? { ...item, status: nextStatus } : item)));
  }

  async function confirmToggleProductStatus() {
    const product = confirmProduct;
    setConfirmProduct(null);
    if (product) {
      await toggleProductStatus(product);
    }
  }

  return (
    <>
      <PageHeader
        title="Ürün Kataloğu"
        description="Onaylı ürün veritabanını, görsel durumlarını ve alternatif isimleri yönetin."
        actions={
          canEditCatalog ? (
            <>
              <Button onClick={() => setIsAdding(true)}>Ürün Ekle</Button>
              <Button variant="primary">Excel İçe Aktar</Button>
            </>
          ) : null
        }
      />

      <FilterBar
        searchPlaceholder="Ürün, barkod, marka veya alternatif isim ara"
        searchValue={searchTerm}
        onSearchChange={(event) => setSearchTerm(event.target.value)}
      >
        <FilterSelect
          label="Marka"
          value={filters.brandId}
          onChange={(value) => updateFilter("brandId", value)}
          options={[{ id: "all", name: "Tüm markalar" }, ...brandOptions]}
        />
        <FilterSelect
          label="Kategori"
          value={filters.categoryId}
          onChange={(value) => updateFilter("categoryId", value)}
          options={[{ id: "all", name: "Tüm kategoriler" }, ...categoryOptions]}
        />
        <FilterSelect
          label="Görsel Durumu"
          value={filters.imageStatus}
          onChange={(value) => updateFilter("imageStatus", value)}
          options={[
            { id: "all", name: "Tümü" },
            { id: "with", name: "Görsel var" },
            { id: "without", name: "Görsel yok" },
          ]}
        />
        <FilterSelect
          label="Aktif/Pasif"
          value={filters.status}
          onChange={(value) => updateFilter("status", value)}
          options={[
            { id: "all", name: "Tümü" },
            { id: "Aktif", name: "Aktif" },
            { id: "Pasif", name: "Pasif" },
          ]}
        />
      </FilterBar>

      {apiError ? <p className="inline-result inline-result-warning">{apiError}</p> : null}
      {successMessage ? <p className="inline-result">{successMessage}</p> : null}

      <Card title="Katalog Ürünleri" action={<span className="card-summary">{filteredProducts.length} ürün</span>}>
        {isLoading ? <p className="inline-result">Ürünler yükleniyor...</p> : null}
        {!isLoading && filteredProducts.length === 0 ? (
          <p className="catalog-empty">Bu filtrelerle eşleşen ürün bulunamadı.</p>
        ) : null}
        {!isLoading && filteredProducts.length > 0 ? (
          <Table
            columns={[
              "Görsel",
              "Ürün Adı",
              "Marka",
              "Barkod",
              "Kategori",
              "Alternatif İsimler",
              "Kullanım",
              "Durum",
              canEditCatalog ? "Aksiyonlar" : null,
            ].filter(Boolean)}
          >
            {filteredProducts.map((product) => (
              <tr key={product.id}>
                <td>
                  <ProductThumbnail label={product.name} hasImage={product.imageStatus !== "Görsel yok"} />
                </td>
                <td>
                  <strong>{product.name}</strong>
                  <small>{[product.packageSize, product.packageType].filter(Boolean).join(" · ") || "-"}</small>
                </td>
                <td>{product.brand || "Marka yok"}</td>
                <td>{product.barcode}</td>
                <td>{product.category || "Kategori yok"}</td>
                <td>{(product.alternativeNames || []).length} isim</td>
                <td>{product.usageCount} kampanya</td>
                <td>
                  <StatusBadge status={product.status} />
                </td>
                {canEditCatalog ? (
                  <td>
                    <div className="table-actions">
                      <button className="table-action" type="button" onClick={() => setEditingProduct(product)}>
                        Düzenle
                      </button>
                      <button
                        className="table-action"
                        type="button"
                        onClick={() => setConfirmProduct(product)}
                        disabled={isTogglingId === product.id}
                      >
                        {isTogglingId === product.id
                          ? "Güncelleniyor..."
                          : product.status === "Aktif"
                            ? "Pasifleştir"
                            : "Aktifleştir"}
                      </button>
                    </div>
                  </td>
                ) : null}
              </tr>
            ))}
          </Table>
        ) : null}
      </Card>

      {canEditCatalog && (editingProduct || isAdding) ? (
        <ProductFormModal
          product={editingProduct}
          brands={brandOptions}
          categories={categoryOptions}
          onClose={closeModal}
          onSave={saveProduct}
          isSaving={isSaving}
          error={modalError}
        />
      ) : null}
      <ConfirmDialog
        isOpen={Boolean(confirmProduct)}
        title="Ürün durumunu değiştir"
        description={
          confirmProduct
            ? `${confirmProduct.name} ürünü ${confirmProduct.status === "Aktif" ? "pasifleştirilecek" : "aktifleştirilecek"}. Devam edilsin mi?`
            : ""
        }
        confirmLabel={confirmProduct?.status === "Aktif" ? "Pasifleştir" : "Aktifleştir"}
        onCancel={() => setConfirmProduct(null)}
        onConfirm={confirmToggleProductStatus}
        isLoading={Boolean(confirmProduct && isTogglingId === confirmProduct.id)}
      />
    </>
  );
}
