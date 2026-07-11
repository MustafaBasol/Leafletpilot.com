import { apiClient } from "./client.js";

export function listTemplates(params, marketId) {
  return apiClient.get("/templates", { params, marketId });
}

export function getTemplate(templateId, marketId) {
  return apiClient.get(`/templates/${templateId}`, { marketId });
}

export function createTemplate(payload, marketId) {
  return apiClient.post("/templates", payload, { marketId });
}

export function updateTemplate(templateId, payload, marketId) {
  return apiClient.patch(`/templates/${templateId}`, payload, { marketId });
}

export function getTemplatePreviewHtml(templateId, marketId) {
  return apiClient.get(`/templates/${templateId}/preview-html`, { marketId });
}
