import { useEffect, useState } from "react";
import { canMutateCatalog, getSelectedMarketId } from "../api/authSession.js";
import { isRealApiEnabled } from "../api/config.js";
import { createCategory, listCategories, updateCategory } from "../api/catalogApi.js";
import { Button, Card, Checkbox, Input, PageHeader, StatusBadge, Table } from "../components/ui/index.js";

export function Categories() {
  const marketId = getSelectedMarketId();
  const canEdit = canMutateCatalog();
  const [items, setItems] = useState([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(isRealApiEnabled);
  const [editingId, setEditingId] = useState(null);
  const [editName, setEditName] = useState("");
  const [editActive, setEditActive] = useState(true);
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState("");

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

  function startEdit(item) {
    setEditingId(item.id);
    setEditName(item.name);
    setEditActive(item.is_active !== false);
    setEditError("");
  }

  function cancelEdit() {
    setEditingId(null);
    setEditError("");
  }

  async function saveEdit(item) {
    const trimmed = editName.trim();
    if (!trimmed) return;
    setEditSaving(true);
    setEditError("");
    try {
      const payload = { name: trimmed, is_active: editActive };
      const updated = isRealApiEnabled ? await updateCategory(item.id, payload, marketId) : { ...item, ...payload };
      setItems((current) => current.map((existing) => (existing.id === item.id ? { ...existing, ...updated } : existing)));
      setEditingId(null);
    } catch (reason) {
      setEditError(reason.message || "Kategori güncellenemedi.");
    } finally {
      setEditSaving(false);
    }
  }

  const columns = canEdit
    ? ["Sıra", "Kategori", "Slug", "Durum", "Aksiyonlar"]
    : ["Sıra", "Kategori", "Slug", "Durum"];

  return (
    <>
      <PageHeader title="Kategoriler" description="Flyer ürünlerini düzenli ve markete özel tutun." />
      {error ? <p className="inline-result inline-result-warning" role="alert">{error}</p> : null}
      {canEdit ? (
        <Card title={items.length ? "Yeni kategori ekle" : "İlk kategorinizi oluşturun"}>
          <form className="inline-form" onSubmit={addCategory}>
            <Input label="Kategori adı" value={name} onChange={(event) => setName(event.target.value)} placeholder="Örn. Süt ürünleri" />
            <Button variant="primary" type="submit" disabled={!name.trim()}>Kategori ekle</Button>
          </form>
        </Card>
      ) : null}
      <Card title="Market kategorileri" action={<span className="card-summary">{items.length} kategori</span>}>
        {loading ? <p className="inline-result">Kategoriler yükleniyor...</p> : null}
        {!loading && !items.length ? <p className="catalog-empty">Henüz kategori yok. Ürün eklemeden önce ilk kategorinizi oluşturun.</p> : null}
        {editError ? <p className="inline-result inline-result-warning" role="alert">{editError}</p> : null}
        {!loading && items.length ? (
          <Table columns={columns}>
            {items.map((item) => {
              const isEditing = editingId === item.id;
              return (
                <tr key={item.id}>
                  <td>{(item.sort_order ?? 0) + 1}</td>
                  <td>
                    {isEditing ? (
                      <input
                        className="table-inline-input"
                        value={editName}
                        onChange={(event) => setEditName(event.target.value)}
                        aria-label="Kategori adı"
                        autoFocus
                      />
                    ) : (
                      <strong>{item.name}</strong>
                    )}
                  </td>
                  <td>{item.slug}</td>
                  <td>
                    {isEditing ? (
                      <Checkbox label="Aktif" checked={editActive} onChange={(event) => setEditActive(event.target.checked)} />
                    ) : (
                      <StatusBadge status={item.is_active === false ? "Pasif" : "Aktif"} />
                    )}
                  </td>
                  {canEdit ? (
                    <td className="table-actions">
                      {isEditing ? (
                        <>
                          <Button variant="primary" onClick={() => saveEdit(item)} disabled={editSaving || !editName.trim()}>
                            {editSaving ? "Kaydediliyor..." : "Kaydet"}
                          </Button>
                          <Button onClick={cancelEdit} disabled={editSaving}>Vazgeç</Button>
                        </>
                      ) : item.is_global ? (
                        <span className="table-hint">Global kategori</span>
                      ) : (
                        <Button onClick={() => startEdit(item)}>Düzenle</Button>
                      )}
                    </td>
                  ) : null}
                </tr>
              );
            })}
          </Table>
        ) : null}
      </Card>
    </>
  );
}
