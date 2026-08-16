import test from "node:test";
import assert from "node:assert/strict";
import { getPublicPlans, submitSignupRequest } from "./publicApi.js";

test("getPublicPlans fetches the public plans endpoint without auth or market headers", async () => {
  const originalFetch = globalThis.fetch;
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return { ok: true, status: 200, text: async () => JSON.stringify([{ code: "starter" }]) };
  };
  try {
    const plans = await getPublicPlans();
    assert.match(captured.url, /\/public\/plans$/);
    assert.equal(captured.options.method, "GET");
    assert.equal(captured.options.headers.Authorization, undefined);
    assert.equal(captured.options.headers["X-Market-Id"], undefined);
    assert.deepEqual(plans, [{ code: "starter" }]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("submitSignupRequest still posts to /public/signup-requests", async () => {
  const originalFetch = globalThis.fetch;
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return { ok: true, status: 202, text: async () => JSON.stringify({ ok: true }) };
  };
  try {
    await submitSignupRequest({ email: "a@b.com" });
    assert.match(captured.url, /\/public\/signup-requests$/);
    assert.equal(captured.options.method, "POST");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
