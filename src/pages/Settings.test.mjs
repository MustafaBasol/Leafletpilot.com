import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const settingsSource = await readFile(new URL("./Settings.jsx", import.meta.url), "utf8");
const navSource = await readFile(new URL("../routes/routes.js", import.meta.url), "utf8");

test("Settings center is present in management navigation", () => {
  assert.match(navSource, /\{ label: "Ayarlar", path: "\/settings", icon: "settings" \}/);
});

test("Settings loads and saves the real market settings API", () => {
  assert.match(settingsSource, /getMarketSettings\(marketId\)/);
  assert.match(settingsSource, /updateMarketSettings\(payload, marketId\)/);
  assert.match(settingsSource, /useEffect\(\(\) => \{ load\(\); \}, \[marketId\]\)/);
});

test("Settings reuses logo endpoints and exposes brochure visibility controls", () => {
  assert.match(settingsSource, /uploadMarketLogo\(file, marketId\)/);
  assert.match(settingsSource, /removeMarketLogo\(marketId\)/);
  for (const preference of ["show_logo", "show_address", "show_phone", "show_website", "show_instagram", "show_facebook"]) {
    assert.match(settingsSource, new RegExp(preference));
  }
});