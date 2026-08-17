import { apiClient } from "./client.js";

export function getSubscription(marketId) {
  return apiClient.get("/billing/subscription", { marketId });
}

export function listInvoices(params, marketId) {
  return apiClient.get("/billing/invoices", { params, marketId });
}

export function startCheckout(planCode, marketId) {
  return apiClient.post("/billing/checkout", { plan_code: planCode }, { marketId });
}

export function openPortal(marketId) {
  return apiClient.post("/billing/portal", {}, { marketId });
}

export function previewChangePlan(planCode, marketId) {
  return apiClient.post("/billing/change-plan-preview", { plan_code: planCode }, { marketId });
}

export function changePlan(planCode, marketId) {
  return apiClient.post("/billing/change-plan", { plan_code: planCode }, { marketId });
}

export function cancelSubscription(marketId) {
  return apiClient.post("/billing/cancel", {}, { marketId });
}

export function resumeSubscription(marketId) {
  return apiClient.post("/billing/resume", {}, { marketId });
}
