import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("./MarketCatalog.jsx", import.meta.url), "utf8");
const apiSource = await readFile(new URL("../api/catalogApi.js", import.meta.url), "utf8");

test("local creation is an explicit post-match decision and uploads an optional image after creation", () => {
  const savePrivate = source.slice(source.indexOf("async function savePrivate"), source.indexOf("async function saveEdit"));
  assert.match(savePrivate, /if \(!matchResult\) \{ await findMatches\(\); return; \}/);
  assert.match(savePrivate, /validateImageFile\(form\.imageFile\)/);
  assert.match(savePrivate, /createPrivateProduct\(privateProductPayload\(form, matchResult\.match_type\)/);
  assert.match(savePrivate, /uploadPrivateProductImage\(created\.id, imageFile/);
  assert.match(savePrivate, /Yerel ürün oluşturuldu ancak görsel yüklenemedi/);
  assert.match(source, /allow_global_match_override: \["exact", "strong", "ambiguous"\]\.includes\(matchType\)/);
  assert.match(source, /Yerel ürün olarak devam et/);
});

test("create image picker keeps preview, replacement, and clearing behavior", () => {
  assert.match(source, /accept="image\/png,image\/jpeg,image\/webp"/);
  assert.match(source, /value\.imageFile \? value\.imageFile\.name/);
  assert.match(source, /ImagePreview file=\{value\.imageFile\}/);
  assert.match(source, /onChange\("imageFile", null\)/);
  assert.match(source, /showImagePicker matchResult=\{matchResult\}/);
});

test("matching uses the focused backend endpoint and renders bounded candidate actions", () => {
  const findMatches = source.slice(source.indexOf("async function findMatches"), source.indexOf("async function adopt(item)"));
  assert.match(apiSource, /matchGlobalProducts\(payload, marketId\).*post\("\/catalog\/products\/match"/s);
  assert.match(findMatches, /catalogApi\.matchGlobalProducts/);
  for (const field of ["name", "barcode", "brand", "package_size", "package_type", "package_amount", "package_unit", "package_type_canonical"]) {
    assert.match(findMatches, new RegExp(`${field}:`));
  }
  assert.match(source, /Eşleşme Ara/);
  assert.match(source, /Global ürünü kullan/);
  assert.match(source, /candidate\.product_id/);
});

test("ambiguous matches cannot expose the adoption action", () => {
  assert.match(source, /const adoptableMatchTypes = new Set\(\["exact", "strong"\]\)/);
  assert.match(source, /const canAdopt = adoptableMatchTypes\.has\(result\?\.match_type\)/);
  assert.match(source, /Belirsiz sonuçlar otomatik olarak kullanılmaz/);
  assert.match(source, /canAdopt \? <Button[^>]+onClick=\{\(\) => onAdopt\(candidate\)\}/);
});

test("identity edits invalidate stale matching responses", () => {
  assert.match(source, /const identityFields = new Set/);
  assert.match(source, /if \(identityFields\.has\(key\)\) invalidateMatch\(\)/);
  assert.match(source, /const revision = \+\+matchRevision\.current/);
  assert.match(source, /if \(matchRevision\.current === revision\) setMatchResult\(result\)/);
});

test("a no-match result keeps mutation-time server rechecking authoritative", () => {
  assert.match(source, /function privateProductPayload\(value, matchType\)/);
  assert.match(source, /allow_global_match_override: \["exact", "strong", "ambiguous"\]\.includes\(matchType\)/);
  assert.match(source, /privateProductPayload\(form, matchResult\.match_type\)/);
  assert.doesNotMatch(source, /allow_global_match_override: true/);
});

test("matched adoption preserves market settings and optional image without copying typed identity", () => {
  const adoptMatched = source.slice(source.indexOf("async function adoptMatched"), source.indexOf("async function savePrivate"));
  assert.match(adoptMatched, /adoptSharedProduct\(candidate\.product_id, \{ product_id: candidate\.product_id, \.\.\.marketSettingsPayload\(form\) \}/);
  assert.match(adoptMatched, /uploadProductOverride\(adopted\.id, form\.imageFile/);
  assert.doesNotMatch(adoptMatched, /privateProductPayload/);
  assert.doesNotMatch(adoptMatched, /display_name_override|private_brand_text|private_package_size/);
});

test("edit modal omits create-only matching and keeps market image actions", () => {
  const editModal = source.slice(source.indexOf("{editing ? <Modal"));
  assert.doesNotMatch(editModal, /showImagePicker/);
  assert.doesNotMatch(editModal, /onMatch=|onAdopt=/);
  assert.match(editModal, /ref=\{fileInput\} type="file"/);
  assert.match(editModal, /Market görseli yükle/);
  assert.match(editModal, /Görseli değiştir/);
  assert.match(editModal, /Market görselini kaldır/);
});

test("edit uses raw overrides and separates local from global name semantics", () => {
  const openEdit = source.slice(source.indexOf("function openEdit"), source.indexOf("async function loadMine"));
  const saveEdit = source.slice(source.indexOf("async function saveEdit"), source.indexOf("async function toggle"));
  assert.match(openEdit, /const overrides = item\.override_values \|\| \{\}/);
  assert.match(openEdit, /private_name: local \?/);
  assert.match(openEdit, /display_name_override: local \?/);
  assert.match(saveEdit, /local \? "private_name" : "display_name_override"/);
  assert.match(saveEdit, /if \(local && !editing\.private_name\?\.trim\(\)\)/);
  assert.match(saveEdit, /updateMyProduct\(editing\.id, productFields/);
  assert.doesNotMatch(saveEdit, /matchGlobalProducts|adoptSharedProduct|upload.*Image/);
});

test("global edit explains inherited and effective values without pinning effective prices", () => {
  assert.match(source, /function InheritedSummary/);
  assert.match(source, /Globalden gelen/);
  assert.match(source, /Şu an gösterilen/);
  assert.match(source, /effective_values: \{ \.\.\.item \}/);
  assert.match(source, /const effective = item\.effective_values \|\| item/);
  assert.match(source, /regular_price: overrides\.regular_price \?\? \(local \? item\.regular_price \?\? "" : ""\)/);
  assert.match(source, /promo_price: overrides\.promo_price \?\? \(local \? item\.promo_price \?\? "" : ""\)/);
});

test("switching create and edit clears create-only state", () => {
  assert.match(source, /function resetCreateForm\(\) \{ invalidateMatch\(\); setForm\(emptyForm\); setEditing\(null\)/);
  assert.match(source, /function openEdit\(item\) \{\s+resetCreateForm\(\)/);
  assert.match(source, /imageFile: undefined/);
  assert.match(source, /onClick=\{\(\) => openEdit\(item\)\}/);
});

test("create-private action activates and focuses the matching form", () => {
  assert.match(source, /action === "create-private"/);
  assert.match(source, /nameInput\.current\?\.focus\(\)/);
  assert.match(source, /leafletpilot:catalog-create/);
});

test("catalog source state and filters use the explicit backend source contract", () => {
  assert.match(source, /includes\(item\.source_state\)/);
  assert.match(source, /sourceState\(item\) === source/);
  assert.match(source, /Global Ürün/);
  assert.match(source, /Yerel Ürün/);
  assert.match(source, /Market Tarafından Düzenlenmiş/);
  assert.match(source, /aria-label="Kaynak filtresi"/);
  assert.match(source, /aria-label="Durum filtresi"/);
});

test("successful image replacement changes the thumbnail cache key", () => {
  const upload = source.slice(source.indexOf("async function upload"), source.indexOf("async function removeImage"));
  assert.match(upload, /await catalogApi\.uploadProductOverride/);
  assert.match(upload, /setImageRevision\(\(current\) => current \+ 1\)/);
  assert.match(source, /refreshKey=\{`\$\{item\.id\}:\$\{imageRevision\}`\}/);
  assert.match(source, /refreshKey=\{`\$\{editing\.id\}:\$\{imageRevision\}`\}/);
});
