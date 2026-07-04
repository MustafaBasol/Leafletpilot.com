import { useEffect, useMemo, useState } from "react";
import { products as initialProducts } from "../data/mockData.js";
import { isRealApiEnabled } from "../api/config.js";
import {
  createCatalogProduct,
  getProductCatalogData,
  updateCatalogProduct,
  updateCatalogProductStatus,
} from "../data/dataSource.js";
import {
  Button,
  Card,
  FilterBar,
  Input,
  Modal,
  PageHeader,
  ProductThumbnail,
  SelectPlaceholder,
  StatusBadge,
  Table,
} from "../components/ui/index.js";

const emptyProduct = {
  name: "",
  shortName: "",
  brand: "",
  category: "",
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

function FieldSelect({ label, value, onChange, options }) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value || ""} onChange={(event) => onChange(event.target.value)} aria-label={label}>
        <option value="">Seçilmedi</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </select>
    </label>
  );
}

function ProductFormModal({ product, brands, categories, onClose, onSave, isSaving, error }) {
  const [form, setForm] = useState(
    product
      ? { ...product, alternativeNamesText: (product.alternativeNames || []).join(", ") }
      : { ...emptyProduct },
  );

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  return (
    <Modal
      title={product ? "Ürünü Düzenle" : "Ürün Ekle"}
      description="Katalogda kullanılacak ürün bilgilerini ve alternatif isimleri yönetin."
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose} disabled={isSaving}>İptal</Button>
          <Button variant="primary" onClick={() => onSave(form)} disabled={isSaving}>
            {isSaving ? "Kaydediliyor..." : "Kaydet"}
          </Button>
        </>
      }
    >
      {error ? <p className="inline-result inline-result-warning">{error}</p> : null}
      <div className="product-form-layout">
        <div className="form-grid modal-form-grid">
          <Input label="Ürün Adı" value={form.name} onChange={(event) => updateField("name", event.target.value)} />
          <Input
            label="Kısa Ürün Adı"
            value={form.shortName}
            onChange={(event) => updateField("shortName", event.target.value)}
          />
          {isRealApiEnabled ? (
            <FieldSelect label="Marka" value={form.brandId} onChange={(value) => updateField("brandId", value)} options={brands} />
          ) : (
            <Input label="Marka" value={form.brand} onChange={(event) => updateField("brand", event.target.value)} />
          )}
          {isRealApiEnabled ? (
            <FieldSelect
              label="Kategori"
              value={form.categoryId}
              onChange={(value) => updateField("categoryId", value)}
              options={categories}
            />
          ) : (
            <Input label="Kategori" value={form.category} onChange={(event) => updateField("category", event.target.value)} />
          )}
          <Input label="Barkod" value={form.barcode} onChange={(event) => updateField("barcode", event.target.value)} />
          <Input
            label="Paket Boyutu"
            value={form.packageSize}
            onChange={(event) => updateField("packageSize", event.target.value)}
          />
          <Input
            label="Paket Tipi"
            value={form.packageType}
            onChange={(event) => updateField("packageType", event.target.value)}
          />
          <SelectPlaceholder label="Durum" value={form.status} />
          <label className="field field-full">
            <span>Alternatif İsimler</span>
            <textarea
              value={form.alternativeNamesText}
              onChange={(event) => updateField("alternativeNamesText", event.target.value)}
            />
          </label>
        </div>
        <div className="upload-zone image-upload">
          <strong>Ürün Görseli</strong>
          <p>PNG ürün görseli için yükleme alanı. Bu fazda gerçek dosya yüklenmez.</p>
        </div>
      </div>
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
  const [apiError, setApiError] = useState("");
  const [modalError, setModalError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  async function loadCatalog() {
    if (!isRealApiEnabled) return;

    try {
      setIsLoading(true);
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
  }, []);

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

  return (
    <>
      <PageHeader
        title="Ürün Kataloğu"
        description="Onaylı ürün veritabanını, görsel durumlarını ve alternatif isimleri yönetin."
        actions={
          <>
            <Button onClick={() => setIsAdding(true)}>Ürün Ekle</Button>
            <Button variant="primary">Excel İçe Aktar</Button>
          </>
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
              "Aksiyonlar",
            ]}
          >
            {filteredProducts.map((product) => (
              <tr key={product.id}>
                <td>
                  <ProductThumbnail label={product.name} hasImage={product.imageStatus !== "Görsel yok"} />
                </td>
                <td>
                  <strong>{product.name}</strong>
                  <small>
                    {[product.packageSize, product.packageType].filter(Boolean).join(" · ") || "-"}
                  </small>
                </td>
                <td>{product.brand || "Marka yok"}</td>
                <td>{product.barcode}</td>
                <td>{product.category || "Kategori yok"}</td>
                <td>{(product.alternativeNames || []).length} isim</td>
                <td>{product.usageCount} kampanya</td>
                <td>
                  <StatusBadge status={product.status} />
                </td>
                <td>
                  <div className="table-actions">
                    <button className="table-action" type="button" onClick={() => setEditingProduct(product)}>
                      Düzenle
                    </button>
                    <button
                      className="table-action"
                      type="button"
                      onClick={() => toggleProductStatus(product)}
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
              </tr>
            ))}
          </Table>
        ) : null}
      </Card>

      {editingProduct || isAdding ? (
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
    </>
  );
}
