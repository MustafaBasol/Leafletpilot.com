import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const pageSource = await readFile(new URL("./MarketCatalog.jsx", import.meta.url), "utf8");
const apiSource = await readFile(new URL("../api/catalogApi.js", import.meta.url), "utf8");

test("renders a compact deterministic global candidate with explainable evidence", () => {
  assert.match(pageSource, /className="catalog-match-candidate"/);
  assert.match(pageSource, /candidate\.name/);
  assert.match(pageSource, /candidate\.brand \|\| "Marka belirtilmedi"/);
  assert.match(pageSource, /packageLabel\(candidate\)/);
  assert.match(pageSource, /candidate\.image_url/);
  assert.match(pageSource, /matchReasonLabel\(candidate\.match_reason \|\| result\.match_reason\)/);
  assert.match(pageSource, /Tam eşleşme bulundu/);
  assert.match(pageSource, /Güçlü eşleşme bulundu/);
  assert.match(pageSource, /Belirsiz sonuçlar otomatik olarak kullanılmaz/);
});

test("matching is an explicit bounded action and stale identity results are invalidated", () => {
  assert.match(pageSource, /Eşleşme Ara/);
  assert.match(pageSource, /type="button" onClick=\{onMatch\}/);
  assert.match(pageSource, /async function findMatches\(event\)/);
  assert.match(pageSource, /event\.currentTarget\.form\.reportValidity\(\)/);
  assert.match(pageSource, /catalogApi\.matchGlobalProducts\(\{/);
  assert.match(pageSource, /const revision = \+\+matchRevision\.current/);
  assert.match(pageSource, /if \(identityFields\.has\(key\)\) invalidateMatch\(\)/);

  const effects = pageSource.slice(
    pageSource.indexOf("useEffect(() => { loadMine"),
    pageSource.indexOf("const visibleMine"),
  );
  assert.doesNotMatch(effects, /matchGlobalProducts|findMatches/);
});

test("market switches invalidate tenant state and reject stale catalog responses", () => {
  assert.match(pageSource, /const marketScope = useRef\(marketId\)/);
  assert.match(pageSource, /marketScope\.current === requestedMarketId/);
  assert.match(pageSource, /resetCreateForm\(\); setMine\(\[\]\); setShared\(\[\]\)/);
  assert.match(pageSource, /if \(tab === "shared"\) loadShared\(\); \}, \[tab, marketId\]\)/);
});

test("adopt action uses the selected global id and never adopts an ambiguous result", () => {
  assert.match(pageSource, /const adoptableMatchTypes = new Set\(\["exact", "strong"\]\)/);
  assert.match(pageSource, /Global ürünü kullan/);
  assert.match(pageSource, /onClick=\{\(\) => onAdopt\(candidate\)\}/);

  const adopt = pageSource.slice(
    pageSource.indexOf("async function adoptMatched"),
    pageSource.indexOf("async function savePrivate"),
  );
  assert.match(adopt, /catalogApi\.adoptSharedProduct\(candidate\.product_id/);
  assert.match(adopt, /product_id: candidate\.product_id/);
  assert.doesNotMatch(adopt, /createPrivateProduct|link-global/);
});

test("local continuation is deliberate and sends the authoritative override flag", () => {
  assert.match(pageSource, /Yerel ürün olarak devam et/);
  assert.match(
    pageSource,
    /allow_global_match_override: \["exact", "strong", "ambiguous"\]\.includes\(matchType\)/,
  );
  assert.doesNotMatch(
    pageSource,
    /allow_global_match_override: \[[^\]]*"none"/,
  );

  const savePrivate = pageSource.slice(
    pageSource.indexOf("async function savePrivate"),
    pageSource.indexOf("async function saveEdit"),
  );
  assert.match(savePrivate, /if \(!matchResult\) \{ await findMatches\(\); return; \}/);
  assert.match(
    savePrivate,
    /catalogApi\.createPrivateProduct\(privateProductPayload\(form, matchResult\.match_type\)/,
  );
  assert.doesNotMatch(savePrivate, /adoptSharedProduct|link-global/);
});

test("source badges use the exact Turkish global local and override labels", () => {
  assert.match(pageSource, /return "Global \+ Market Düzenlemesi"/);
  assert.match(pageSource, /return "Global Ürün"/);
  assert.match(pageSource, /return "Yerel Ürün"/);
  assert.match(pageSource, /<td>\{sourceLabel\(item\)\}<\/td>/);
  assert.match(pageSource, /<strong>Globalden gelen<\/strong>/);
  assert.match(pageSource, /<strong>Şu an gösterilen<\/strong>/);
});

test("catalog API adapter posts match input with market scope", () => {
  assert.match(
    apiSource,
    /matchGlobalProducts\(payload, marketId\).*apiClient\.post\("\/catalog\/products\/match", payload, \{ marketId \}\)/,
  );
});

test("editing updates the existing market row without matching adopting or relinking", () => {
  const saveEdit = pageSource.slice(
    pageSource.indexOf("async function saveEdit"),
    pageSource.indexOf("async function toggle"),
  );
  assert.match(saveEdit, /catalogApi\.updateMyProduct\(editing\.id/);
  assert.doesNotMatch(
    saveEdit,
    /matchGlobalProducts|findMatches|adoptSharedProduct|createPrivateProduct|linkGlobal|link-global/,
  );

  const editModal = pageSource.slice(pageSource.indexOf("{editing ? <Modal"));
  assert.match(editModal, /isGlobalEdit=\{sourceState\(editing\) !== "local"\}/);
  assert.doesNotMatch(editModal, /onMatch=|onAdopt=/);
});
