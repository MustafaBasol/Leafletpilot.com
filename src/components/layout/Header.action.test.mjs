import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("./Header.jsx", import.meta.url), "utf8");

test("header product action uses the create-private route and supports repeated clicks", () => {
  assert.match(source, /href="#\/products\?action=create-private"/);
  assert.match(source, /leafletpilot:catalog-create/);
  assert.match(source, /window\.location\.hash === "#\/products\?action=create-private"/);
});
