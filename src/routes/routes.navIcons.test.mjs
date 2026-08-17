import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { navGroups } from "./routes.js";

const iconSource = await readFile(new URL("../components/ui/Icon.jsx", import.meta.url), "utf8");

const EXPECTED_ICONS = {
  "/dashboard": "dashboard",
  "/campaigns": "megaphone",
  "/campaigns/new": "plusCircle",
  "/products": "box",
  "/categories": "tags",
  "/brands": "badge",
  "/templates": "layoutTemplate",
  "/team": "users",
  "/settings/billing": "creditCard",
};

test("every sidebar nav item declares an icon name that exists in the icon library", () => {
  for (const group of navGroups) {
    for (const item of group.items) {
      assert.ok(item.icon, `${item.path} must declare an icon`);
      assert.match(iconSource, new RegExp(`\\b${item.icon}: \\(`), `Icon library must define "${item.icon}" used by ${item.path}`);
    }
  }
});

test("sidebar items use distinct, semantically matched icons for the reworked groups", () => {
  const byPath = Object.fromEntries(navGroups.flatMap((group) => group.items).map((item) => [item.path, item.icon]));
  for (const [path, expectedIcon] of Object.entries(EXPECTED_ICONS)) {
    assert.equal(byPath[path], expectedIcon, `${path} should use the "${expectedIcon}" icon`);
  }
});

test("active state class hook remains intact for nav links", async () => {
  const sidebarSource = await readFile(new URL("../components/layout/Sidebar.jsx", import.meta.url), "utf8");
  assert.match(sidebarSource, /isActivePath\(currentPath, item\.path\) \? "is-active" : ""/);
  assert.match(sidebarSource, /<Icon name=\{item\.icon\} \/>/);
});
