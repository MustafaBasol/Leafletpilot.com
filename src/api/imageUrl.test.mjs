import test from "node:test";
import assert from "node:assert/strict";
import { fetchImageSource, resolveImageUrl } from "./client.js";

function installBrowserGlobals(token = "test-token") {
  const originalLocalStorage = globalThis.localStorage;
  const originalCreateObjectUrl = URL.createObjectURL;
  const originalRevokeObjectUrl = URL.revokeObjectURL;
  const values = new Map([["leafletpilot_access_token", token]]);
  const revoked = [];

  globalThis.localStorage = { getItem: (key) => values.get(key) || null };
  URL.createObjectURL = () => "blob:test-image";
  URL.revokeObjectURL = (url) => revoked.push(url);

  return () => {
    globalThis.localStorage = originalLocalStorage;
    URL.createObjectURL = originalCreateObjectUrl;
    URL.revokeObjectURL = originalRevokeObjectUrl;
    return revoked;
  };
}

test("relative API image URLs resolve against the API base and use the bearer token", async () => {
  const restore = installBrowserGlobals();
  const originalFetch = globalThis.fetch;
  let request;
  globalThis.fetch = async (url, options) => {
    request = { url, options };
    return { ok: true, blob: async () => new Blob(["image"], { type: "image/png" }) };
  };

  try {
    assert.equal(resolveImageUrl("/api/catalog/my-products/1/image/content"), "http://127.0.0.1:8000/api/catalog/my-products/1/image/content");
    const source = await fetchImageSource("/api/catalog/my-products/1/image/content", { marketId: "market-anadolu" });
    assert.deepEqual(source, { src: "blob:test-image", revoke: true });
    assert.equal(request.url, "http://127.0.0.1:8000/api/catalog/my-products/1/image/content");
    assert.equal(request.options.headers.Authorization, "Bearer test-token");
    assert.equal(request.options.headers["X-Market-Id"], "market-anadolu");
    assert.equal(request.options.cache, "no-store");
  } finally {
    globalThis.fetch = originalFetch;
    restore();
  }
});

test("absolute external image URLs render directly without sending the access token", async () => {
  const restore = installBrowserGlobals();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error("external image should not be fetched by the helper");
  };

  try {
    assert.deepEqual(await fetchImageSource("https://cdn.example.test/product.png"), {
      src: "https://cdn.example.test/product.png",
      revoke: false,
    });
  } finally {
    globalThis.fetch = originalFetch;
    restore();
  }
});

test("failed authenticated image fetch rejects so the thumbnail can render its fallback", async () => {
  const restore = installBrowserGlobals();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: false, status: 403 });

  try {
    await assert.rejects(() => fetchImageSource("/api/catalog/my-products/1/image/content", { marketId: "market-anadolu" }), /403/);
  } finally {
    globalThis.fetch = originalFetch;
    restore();
  }
});

test("changing market context sends a fresh market-scoped image request", async () => {
  const restore = installBrowserGlobals();
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    return { ok: true, blob: async () => new Blob(["image"], { type: "image/png" }) };
  };

  try {
    await fetchImageSource("/api/catalog/my-products/1/image/content", { marketId: "market-anadolu" });
    await fetchImageSource("/api/catalog/my-products/1/image/content", { marketId: "market-avrupa" });
    assert.deepEqual(requests.map(({ options }) => options.headers["X-Market-Id"]), ["market-anadolu", "market-avrupa"]);
    assert.equal(requests.some(({ options }) => options.headers.Authorization === "Bearer test-token"), true);
  } finally {
    globalThis.fetch = originalFetch;
    restore();
  }
});

test("missing market context safely rejects an authenticated API image", async () => {
  const restore = installBrowserGlobals();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error("request should not start without market context");
  };

  try {
    await assert.rejects(() => fetchImageSource("/api/catalog/my-products/1/image/content"), /seçili market/);
  } finally {
    globalThis.fetch = originalFetch;
    restore();
  }
});
