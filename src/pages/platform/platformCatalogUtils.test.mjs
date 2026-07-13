import test from "node:test";
import assert from "node:assert/strict";
import { normalizeOptionalUuid, revokeObjectUrls } from "./platformCatalogUtils.js";

test("normalizes empty catalog selections to null UUID values", () => {
  assert.equal(normalizeOptionalUuid(""), null);
  assert.equal(normalizeOptionalUuid(null), null);
  assert.equal(normalizeOptionalUuid("7f2a"), "7f2a");
});

test("revokes each object URL once, including duplicate references", () => {
  const revoked = [];
  const original = URL.revokeObjectURL;
  URL.revokeObjectURL = (url) => revoked.push(url);
  try {
    revokeObjectUrls({ first: "blob:first", second: "blob:first", third: "blob:third" });
  } finally {
    URL.revokeObjectURL = original;
  }
  assert.deepEqual(revoked.sort(), ["blob:first", "blob:third"]);
});
