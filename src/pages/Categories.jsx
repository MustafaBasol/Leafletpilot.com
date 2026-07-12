import { useEffect, useState } from "react";
import { canMutateCatalog, getSelectedMarketId } from "../api/authSession.js";
import { isRealApiEnabled } from "../api/config.js";
import { createCategory, listCategories } from "../api/catalogApi.js";
import { Button, Card, Input, PageHeader, StatusBadge, Table } from "../components/ui/index.js";

export function Categories() {
  const marketId = getSelectedMarketId();
  const canEdit = canMutateCatalog();
  const [items, setItems] = useState([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(isRealApiEnabled);

  useEffect(() => {
    if (!isRealApiEnabled) return;
    setLoading(true);
    listCategories({ include_global: true, is_active: true, limit: 100 }, marketId)
      .then((response) => setItems(response.items || []))
      .catch((reason) => setError(reason.message || "Kategoriler yüklenemedi."))
      .finally(() => setLoading(false));
  }, [marketId]);

  async function addCategory(event) {
    event.preventDefault();
    if (!name.trim() || !canEdit) return;
    try {
      const created = isRealApiEnabled
        ? await createCategory({ name: name.trim(), sort_order: items.length }, marketId)
        : { id: `category-${Date.now()}`, name: name.trim(), slug: name.trim().toLowerCase(), sort_order: items.length, is_active: true };
      setItems((current) => [...current, created]);
      setName("");
      setError("");
    } catch (reason) {
      setError(reason.message || "Kategori oluşturulamadı.");
    }
  }

  return (
    <>
      <PageHeader title="Kategoriler" description="Flyer ürünlerini düzenli ve markete özel tutun." />
      {error ? <p className="inline-result inline-result-warning">{error}</p> : null}
      {canEdit ? (
        <Card title="İlk kategorinizi oluşturun">
          <form className="inline-form" onSubmit={addCategory}>
            <Input label="Kategori adı" value={name} onChange={(event) => setName(event.target.value)} placeholder="Örn. Süt ürünleri" />
            <Button variant="primary" type="submit" disabled={!name.trim()}>Kategori ekle</Button>
          </form>
        </Card>
      ) : null}
      <Card title="Market kategorileri" action={<span className="card-summary">{items.length} kategori</span>}>
        {loading ? <p className="inline-result">Kategoriler yükleniyor...</p> : null}
        {!loading && !items.length ? <p className="catalog-empty">Henüz kategori yok. Ürün eklemeden önce ilk kategorinizi oluşturun.</p> : null}
        {!loading && items.length ? (
          <Table columns={["Sıra", "Kategori", "Slug", "Durum"]}>
            {items.map((item) => <tr key={item.id}><td>{item.sort_order ?? 0}</td><td><strong>{item.name}</strong></td><td>{item.slug}</td><td><StatusBadge status={item.is_active === false ? "Pasif" : "Aktif"} /></td></tr>)}
          </Table>
        ) : null}
      </Card>
    </>
  );
}
