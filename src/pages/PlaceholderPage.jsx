import { useEffect, useMemo, useState } from "react";
import { isRealApiEnabled } from "../api/config.js";
import { products } from "../data/mockData.js";
import { createCatalogBrand, createCatalogCategory, getCatalogBrands, getCatalogCategories } from "../data/dataSource.js";
import { pageMeta } from "../routes/routes.js";
import {
  Button,
  Card,
  EmptyState,
  FilterBar,
  Input,
  SelectPlaceholder,
  StatusBadge,
  Table,
} from "../components/ui/index.js";

function normalizeSearch(value) {
  return String(value || "")
    .toLocaleLowerCase("tr-TR")
    .trim();
}

function ProductPreviewTable() {
  return (
    <Table columns={["Ürün", "Marka", "Kategori", "Durum", "Aksiyon"]}>
      {products.slice(0, 5).map((product) => (
        <tr key={product.name}>
          <td>
            <strong>{product.name}</strong>
            <small>{product.price}</small>
          </td>
          <td>{product.brand}</td>
          <td>{product.category}</td>
          <td>
            <StatusBadge status="Onaylandı" />
          </td>
          <td>
            <a className="table-action" href="#/products">
              Düzenle
            </a>
          </td>
        </tr>
      ))}
    </Table>
  );
}

function CatalogAdminPage({ type }) {
  const isBrand = type === "brands";
  const [items, setItems] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [form, setForm] = useState({ name: "", slug: "", isGlobal: false });
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [apiError, setApiError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadItems() {
    try {
      setIsLoading(true);
      const nextItems = isBrand ? await getCatalogBrands() : await getCatalogCategories();
      setItems(nextItems);
      setApiError("");
    } catch (error) {
      setItems([]);
      setApiError(error.message || `${isBrand ? "Markalar" : "Kategoriler"} yüklenemedi.`);
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadItems();
  }, [type]);

  const filteredItems = useMemo(() => {
    const query = normalizeSearch(searchTerm);
    return items.filter((item) => {
      const searchable = normalizeSearch([item.name, item.slug].filter(Boolean).join(" "));
      return !query || searchable.includes(query);
    });
  }, [items, searchTerm]);

  async function saveItem(event) {
    event.preventDefault();
    if (!form.name.trim()) {
      setApiError("İsim alanı zorunlu.");
      return;
    }

    if (!isRealApiEnabled) {
      const localItem = {
        id: `${type}-${Date.now()}`,
        name: form.name.trim(),
        slug: form.slug.trim() || normalizeSearch(form.name).replace(/\s+/g, "-"),
        is_active: true,
        is_global: form.isGlobal,
        parent_id: null,
      };
      setItems((current) => [localItem, ...current]);
      setForm({ name: "", slug: "", isGlobal: false });
      setNotice(`${isBrand ? "Marka" : "Kategori"} yerel demo listeye eklendi.`);
      setApiError("");
      return;
    }

    try {
      setIsSaving(true);
      setApiError("");
      if (isBrand) {
        await createCatalogBrand(form);
      } else {
        await createCatalogCategory(form);
      }
      setForm({ name: "", slug: "", isGlobal: false });
      setNotice(`${isBrand ? "Marka" : "Kategori"} kaydedildi.`);
      await loadItems();
    } catch (error) {
      setApiError(error.message || `${isBrand ? "Marka" : "Kategori"} kaydedilemedi.`);
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <>
      <section className="page-heading">
        <div>
          <h2>{isBrand ? "Markalar" : "Kategoriler"}</h2>
          <p>
            {isBrand
              ? "Katalog markalarını arayın, görüntüleyin ve yeni marka ekleyin."
              : "Katalog kategorilerini arayın, görüntüleyin ve yeni kategori ekleyin."}
          </p>
        </div>
      </section>

      <FilterBar
        searchPlaceholder={isBrand ? "Marka adı veya slug ara" : "Kategori adı veya slug ara"}
        searchValue={searchTerm}
        onSearchChange={(event) => setSearchTerm(event.target.value)}
      />

      {apiError ? <p className="inline-result inline-result-warning">{apiError}</p> : null}
      {notice ? <p className="inline-result">{notice}</p> : null}

      <section className="placeholder-grid">
        <Card title={isBrand ? "Yeni Marka" : "Yeni Kategori"} className="span-4">
          <form className="form-grid" onSubmit={saveItem}>
            <Input label="Ad" value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} />
            <Input
              label="Slug"
              value={form.slug}
              placeholder="Boş bırakılırsa backend üretir"
              onChange={(event) => setForm((current) => ({ ...current, slug: event.target.value }))}
            />
            <label className="check-row">
              <input
                type="checkbox"
                checked={form.isGlobal}
                onChange={(event) => setForm((current) => ({ ...current, isGlobal: event.target.checked }))}
              />
              <span>Global kayıt</span>
            </label>
            <Button variant="primary" type="submit" disabled={isSaving}>
              {isSaving ? "Kaydediliyor..." : "Kaydet"}
            </Button>
          </form>
        </Card>

        <Card
          title={isBrand ? "Marka Listesi" : "Kategori Listesi"}
          className="span-8"
          action={<span className="card-summary">{filteredItems.length} kayıt</span>}
        >
          {isLoading ? <p className="inline-result">Liste yükleniyor...</p> : null}
          {!isLoading && filteredItems.length === 0 ? <p className="catalog-empty">Eşleşen kayıt bulunamadı.</p> : null}
          {!isLoading && filteredItems.length ? (
            <Table columns={isBrand ? ["Ad", "Slug", "Kapsam", "Durum"] : ["Ad", "Slug", "Üst Kategori", "Kapsam", "Durum"]}>
              {filteredItems.map((item) => (
                <tr key={item.id || item.slug || item.name}>
                  <td>
                    <strong>{item.name}</strong>
                  </td>
                  <td>{item.slug || "-"}</td>
                  {!isBrand ? <td>{item.parent_id || "-"}</td> : null}
                  <td>{item.is_global ? "Global" : "Market"}</td>
                  <td>
                    <StatusBadge status={item.is_active === false ? "Pasif" : "Aktif"} />
                  </td>
                </tr>
              ))}
            </Table>
          ) : null}
        </Card>
      </section>
    </>
  );
}

export function PlaceholderPage({ path }) {
  const meta = pageMeta[path] || pageMeta["/campaigns"];

  if (path === "/brands") return <CatalogAdminPage type="brands" />;
  if (path === "/categories") return <CatalogAdminPage type="categories" />;

  return (
    <>
      <section className="page-heading">
        <div>
          <h2>{meta.title}</h2>
          <p>{meta.description}</p>
        </div>
        <div className="page-actions">
          <Button variant="primary" href={meta.actionHref}>
            {meta.action}
          </Button>
        </div>
      </section>
      <section className="placeholder-grid">
        <Card title="Filtreler" className="span-12">
          <div className="form-grid">
            <Input label="Arama" placeholder="Kampanya, ürün veya market ara" />
            <SelectPlaceholder label="Durum" value="Tüm durumlar" />
            <SelectPlaceholder label="Market" value="Anadolu Market" />
          </div>
        </Card>
        <Card title="Örnek Liste" className="span-8">
          <ProductPreviewTable />
        </Card>
        <Card className="span-4">
          <EmptyState
            title={`${meta.title} ekranı hazırlandı`}
            text="Bu fazda rota, sayfa iskeleti ve temel bileşenler eklendi. Detaylı iş akışı bir sonraki fazda doldurulacak."
            action={
              <Button variant="secondary" href={meta.actionHref}>
                {meta.action}
              </Button>
            }
          />
        </Card>
      </section>
    </>
  );
}
