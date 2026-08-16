import test from "node:test";
import assert from "node:assert/strict";
import { platformApi } from "./platformApi.js";

function installBrowserGlobals() {
  const values = new Map([["leafletpilot_platform_access_token", "expired-token"]]);
  globalThis.sessionStorage = {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
  globalThis.window = { location: { hash: "#/platform/catalog" } };
  return values;
}

test("image requests use the shared expired-session recovery", async () => {
  const values = installBrowserGlobals();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({
    ok: false,
    status: 401,
    clone: () => ({ json: async () => ({ detail: "Unauthorized" }) }),
  });
  try {
    await assert.rejects(() => platformApi.getGlobalProductImageUrl("product", "image"), { status: 401 });
    assert.equal(values.get("leafletpilot_platform_access_token"), undefined);
    assert.equal(window.location.hash, "#/platform/login");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("updateMarketPlan PATCHes the market plan endpoint with the selected plan code", async () => {
  const values = installBrowserGlobals();
  const originalFetch = globalThis.fetch;
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return { ok: true, text: async () => JSON.stringify({ subscription_plan: "standard" }) };
  };
  try {
    const result = await platformApi.updateMarketPlan("market-1", { subscription_plan: "standard", reason: "Upsell" });
    assert.match(captured.url, /\/platform\/markets\/market-1\/plan$/);
    assert.equal(captured.options.method, "PATCH");
    assert.deepEqual(JSON.parse(captured.options.body), { subscription_plan: "standard", reason: "Upsell" });
    assert.equal(result.subscription_plan, "standard");
  } finally {
    globalThis.fetch = originalFetch;
    values.clear();
  }
});

test("manual image upload sends a browser File as raw PNG bytes with primary=true", async () => {
  const values = installBrowserGlobals();
  const originalFetch = globalThis.fetch;
  const originalFile = globalThis.File;
  const file = new Blob([Uint8Array.of(137, 80, 78, 71)], { type: "image/png" });
  globalThis.File = class File extends Blob { constructor(parts, name, options) { super(parts, options); this.name = name; } };
  const browserFile = new File([file], "coca-cola-1l.png", { type: "image/png" });
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return { ok: true, text: async () => JSON.stringify({ id: "image-id", quality_status: "good" }) };
  };
  try {
    await platformApi.uploadGlobalProductImage("2fda604d-77e9-4aa9-a58b-92522ce3f966", browserFile, { mimeType: browserFile.type, primary: true });
    assert.match(captured.url, /\/images\?primary=true$/);
    assert.equal(captured.options.headers["Content-Type"], "image/png");
    assert.equal(captured.options.body, browserFile);
    assert.equal(captured.options.headers.Authorization, "Bearer expired-token");
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.File = originalFile;
    values.clear();
  }
});
