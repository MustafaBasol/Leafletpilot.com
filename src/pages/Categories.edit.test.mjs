import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const page = readFileSync(new URL("./Categories.jsx", import.meta.url), "utf8");

test("1-based numbering: sort_order is displayed as sort_order + 1, backend value stays untouched", () => {
  assert.match(page, /\{\(item\.sort_order \?\? 0\) \+ 1\}/);
});

test("edit flow updates the item it was invoked on and only sends name/is_active, not slug", () => {
  const saveEdit = page.slice(page.indexOf("async function saveEdit"), page.indexOf("const columns ="));
  assert.match(saveEdit, /const payload = \{ name: trimmed, is_active: editActive \}/);
  assert.doesNotMatch(saveEdit, /slug/);
  assert.match(saveEdit, /await updateCategory\(item\.id, payload, marketId\)/);
  assert.match(
    saveEdit,
    /setItems\(\(current\) => current\.map\(\(existing\) => \(existing\.id === item\.id \? \{ \.\.\.existing, \.\.\.updated \} : existing\)\)\)/,
  );
});

test("edit action is hidden for global categories, matching the backend's rejection of global edits", () => {
  assert.match(page, /item\.is_global \? \(\s*<span className="table-hint">Global kategori<\/span>/);
});

test("create-panel heading is conditional on whether categories already exist", () => {
  assert.match(page, /title=\{items\.length \? "Yeni kategori ekle" : "İlk kategorinizi oluşturun"\}/);
});
