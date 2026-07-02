import { useState } from "react";
import { products as initialProducts } from "../data/mockData.js";
import {
  Button,
  Card,
  FilterBar,
  FilterChip,
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
  barcode: "",
  packageSize: "",
  packageType: "",
  alternativeNamesText: "",
  status: "Aktif",
};

function ProductFormModal({ product, onClose, onSave }) {
  const [form, setForm] = useState(
    product
      ? { ...product, alternativeNamesText: product.alternativeNames.join(", ") }
      : { ...emptyProduct, name: "Yeni Ürün" },
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
          <Button onClick={onClose}>İptal</Button>
          <Button variant="primary" onClick={() => onSave(form)}>
            Kaydet
          </Button>
        </>
      }
    >
      <div className="product-form-layout">
        <div className="form-grid modal-form-grid">
          <Input label="Ürün Adı" value={form.name} onChange={(event) => updateField("name", event.target.value)} />
          <Input
            label="Kısa Ürün Adı"
            value={form.shortName}
            onChange={(event) => updateField("shortName", event.target.value)}
          />
          <Input label="Marka" value={form.brand} onChange={(event) => updateField("brand", event.target.value)} />
          <Input label="Kategori" value={form.category} onChange={(event) => updateField("category", event.target.value)} />
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
  const [products, setProducts] = useState(initialProducts);
  const [editingProduct, setEditingProduct] = useState(null);
  const [isAdding, setIsAdding] = useState(false);

  function closeModal() {
    setEditingProduct(null);
    setIsAdding(false);
  }

  function saveProduct(form) {
    const nextProduct = {
      ...form,
      id: form.id || `product-${Date.now()}`,
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

      <FilterBar searchPlaceholder="Ürün, barkod, marka veya alternatif isim ara">
        <FilterChip label="Marka" />
        <FilterChip label="Kategori" />
        <FilterChip label="Görsel Durumu" />
        <FilterChip label="Aktif/Pasif" value="Aktif" />
      </FilterBar>

      <Card title="Katalog Ürünleri">
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
          {products.map((product) => (
            <tr key={product.id}>
              <td>
                <ProductThumbnail label={product.name} hasImage={product.imageStatus !== "Görsel yok"} />
              </td>
              <td>
                <strong>{product.name}</strong>
                <small>
                  {product.packageSize} · {product.packageType}
                </small>
              </td>
              <td>{product.brand}</td>
              <td>{product.barcode}</td>
              <td>{product.category}</td>
              <td>{product.alternativeNames.length} isim</td>
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
                    onClick={() =>
                      setProducts((current) =>
                        current.map((item) =>
                          item.id === product.id ? { ...item, status: item.status === "Aktif" ? "Pasif" : "Aktif" } : item,
                        ),
                      )
                    }
                  >
                    {product.status === "Aktif" ? "Pasifleştir" : "Aktifleştir"}
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </Table>
      </Card>

      {editingProduct || isAdding ? (
        <ProductFormModal product={editingProduct} onClose={closeModal} onSave={saveProduct} />
      ) : null}
    </>
  );
}
