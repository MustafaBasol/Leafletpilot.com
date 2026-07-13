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
