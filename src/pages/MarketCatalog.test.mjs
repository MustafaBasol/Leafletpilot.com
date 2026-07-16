import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("./MarketCatalog.jsx", import.meta.url), "utf8");

test("private creation validates and uploads an optional image only after creation", () => {
  assert.match(source, /validateImageFile\(form\.imageFile\)/);
  assert.match(source, /createPrivateProduct\(/);
  assert.match(source, /uploadPrivateProductImage\(created\.id, imageFile/);
  assert.match(source, /Özel ürün oluşturuldu ancak görsel yüklenemedi/);
  assert.match(source, /if \(busy\) return/);
});

test("private image picker supports preview, filename, replacement, and clearing", () => {
  assert.match(source, /accept="image\/png,image\/jpeg,image\/webp"/);
  assert.match(source, /imageFile\.name/);
  assert.match(source, /ImagePreview file=\{value\.imageFile\}/);
  assert.match(source, /onChange\("imageFile", null\)/);
  assert.match(source, /nameInput=\{nameInput\} showImagePicker \/>/);
});

test("edit modal omits the create-only image picker and keeps store image actions", () => {
  const editModal = source.slice(source.indexOf("{editing ? <Modal"));
  assert.doesNotMatch(editModal, /Ürün görseli \(isteğe bağlı\)/);
  assert.match(editModal, /ref=\{fileInput\} type="file"/);
  assert.match(editModal, /Mağaza görseli yükle/);
  assert.match(editModal, /Görseli değiştir/);
  assert.match(editModal, /Mağaza görselini kaldır/);
});

test("edit save updates product fields without attempting image upload", () => {
  const saveEdit = source.slice(source.indexOf("async function saveEdit"), source.indexOf("async function toggle"));
  assert.match(saveEdit, /Object\.fromEntries\(editableProductFields\.map/);
  assert.match(saveEdit, /updateMyProduct\(/);
  assert.doesNotMatch(saveEdit, /upload.*Image/);
});

test("switching create and edit clears create-only selected-file state", () => {
  assert.match(source, /function resetCreateForm\(\) \{ setForm\(emptyForm\); setEditing\(null\)/);
  assert.match(source, /function openEdit\(item\) \{ resetCreateForm\(\); setEditing\(\{ \.\.\.item, imageFile: undefined \}\); \}/);
  assert.match(source, /onClick=\{\(\) => openEdit\(item\)\}/);
});

test("create-private action activates and focuses the private form", () => {
  assert.match(source, /action === "create-private"/);
  assert.match(source, /nameInput\.current\?\.focus\(\)/);
  assert.match(source, /leafletpilot:catalog-create/);
});

test("catalog filter toolbar keeps accessible source and status selects", () => {
  assert.match(source, /aria-label="Kaynak filtresi"/);
  assert.match(source, /aria-label="Durum filtresi"/);
  assert.match(source, /<FilterBar/);
});
