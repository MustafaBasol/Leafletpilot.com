import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("./PlanChangeModal.jsx", import.meta.url), "utf8");

test("PlanChangeModal renders nothing until opened", () => {
  assert.match(source, /if \(!isOpen\) return null;/);
});

test("PlanChangeModal shows current plan, target plan, immediate charge, explanation, and next renewal", () => {
  assert.match(source, /Mevcut plan<\/span>/);
  assert.match(source, /<strong>\{currentPlanLabel\}<\/strong>/);
  assert.match(source, /Yeni plan<\/span>/);
  assert.match(source, /<strong>\{targetPlanLabel\}<\/strong>/);
  assert.match(source, /Bugün tahsil edilecek tutar/);
  assert.match(source, /formatMoney\(preview\.immediate_amount_due, preview\.currency\)/);
  assert.match(source, /\{preview\.explanation\}/);
  assert.match(source, /Bir sonraki yenileme tarihi/);
  assert.match(source, /formatDate\(preview\.next_renewal_date\)/);
  assert.match(source, /Bir sonraki yenilemede aylık ücret/);
  assert.match(source, /formatMoney\(preview\.next_renewal_amount, preview\.currency\)/);
});

test("PlanChangeModal shows 'no extra charge' copy when the preview has no immediate charge (downgrade case)", () => {
  assert.match(source, /hasImmediateCharge = Boolean\(preview && preview\.immediate_amount_due > 0\)/);
  assert.match(source, /"Ek ücret yok"/);
});

test("PlanChangeModal blocks confirmation while loading, on error, without a preview, or while already confirming", () => {
  assert.match(
    source,
    /canConfirm = Boolean\(preview\) && !isLoadingPreview && !error && !isConfirming/,
  );
  assert.match(source, /disabled=\{!canConfirm\}/);
});

test("PlanChangeModal disables the close affordance while a confirmation is in flight (no accidental dismiss mid-submit)", () => {
  assert.match(source, /onClose=\{isConfirming \? undefined : onCancel\}/);
  assert.match(source, /disabled=\{isConfirming\}/);
});

test("PlanChangeModal surfaces preview/confirm errors as a polished inline alert", () => {
  assert.match(source, /inline-result inline-result-danger billing-alert/);
});
