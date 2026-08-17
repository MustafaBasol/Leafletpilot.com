import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("./App.jsx", import.meta.url), "utf8");

function pageBody() {
  const start = source.indexOf("function Page({");
  const end = source.indexOf("\nexport function App()");
  assert.ok(start !== -1 && end !== -1, "Page() routing function must exist in App.jsx");
  return source.slice(start, end);
}

test("/settings/billing route matches the query-stripped pathname, not the raw path", () => {
  const body = pageBody();
  assert.match(body, /if \(pathname === "\/settings\/billing"\)/);
  assert.doesNotMatch(body, /if \(path === "\/settings\/billing"\)/);
});

test("Billing route renders the real Billing component with a checkout status prop", () => {
  const body = pageBody();
  const billingMatch = body.match(/if \(pathname === "\/settings\/billing"\) \{\s*return <Billing checkoutStatus=\{([^}]+)\} \/>;/);
  assert.ok(billingMatch, "Billing route must render <Billing checkoutStatus={...} />");
  assert.match(billingMatch[1], /new URLSearchParams\(search\)\.get\("checkout"\)/);
});

test("other single-segment routes also key off the query-stripped pathname (regression: query strings used to fall through to the placeholder scaffold)", () => {
  const body = pageBody();
  for (const routePath of ["/categories", "/templates", "/bot-connections", "/settings", "/team", "/onboarding"]) {
    assert.match(body, new RegExp(`pathname === "${routePath}"`), `${routePath} must match on pathname`);
    assert.doesNotMatch(body, new RegExp(`if \\(path === "${routePath}"\\)`), `${routePath} must not match on the raw (query-bearing) path`);
  }
});

test("PlaceholderPage fallback is only reached after every real route (including billing) has been matched", () => {
  const body = pageBody();
  const billingIndex = body.indexOf('pathname === "/settings/billing"');
  const placeholderIndex = body.indexOf("PlaceholderPage path={pathname}");
  assert.ok(billingIndex !== -1 && placeholderIndex !== -1);
  assert.ok(billingIndex < placeholderIndex, "billing route must be checked before the generic placeholder fallback");
});
