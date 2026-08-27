import test from "node:test";
import assert from "node:assert/strict";
import { canAccessPilotPath } from "./capabilities.js";

test("settings center is visible", () => {
  assert.equal(canAccessPilotPath("/settings"), true);
});

test("explicitly visible descendant of a hidden path is allowed", () => {
  assert.equal(canAccessPilotPath("/settings/billing"), true);
});

test("unrelated descendants of hidden paths remain denied", () => {
  assert.equal(canAccessPilotPath("/markets/123"), false);
  assert.equal(canAccessPilotPath("/files/report.pdf"), false);
  assert.equal(canAccessPilotPath("/reports/weekly"), false);
  assert.equal(canAccessPilotPath("/bot-connections/telegram"), false);
  assert.equal(canAccessPilotPath("/settings/other"), false);
});

test("visible routes remain allowed", () => {
  assert.equal(canAccessPilotPath("/dashboard"), true);
  assert.equal(canAccessPilotPath("/campaigns"), true);
  assert.equal(canAccessPilotPath("/campaigns/new"), true);
  assert.equal(canAccessPilotPath("/products"), true);
  assert.equal(canAccessPilotPath("/templates"), true);
});
