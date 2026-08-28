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

export function getSharedTemplates(marketId) { return apiClient.get("/templates/shared", { marketId }); }
export function getMyTemplates(marketId) { return apiClient.get("/templates/my-templates", { marketId }); }
export function adoptTemplate(templateId, marketId) { return apiClient.post(`/templates/shared/${templateId}/adopt`, {}, { marketId }); }
export function createCustomTemplate(payload, marketId) { return apiClient.post("/templates/custom", payload, { marketId }); }
export function getTemplatePresets(marketId) { return apiClient.get("/templates/presets", { marketId }); }
export function uploadTemplateThumbnail(templateId, file, marketId) {
  return apiClient.post(`/templates/${templateId}/thumbnail`, file, { marketId, headers: { "Content-Type": file.type || "application/octet-stream" } });
}

export function setDefaultTemplate(templateId, marketId) { return apiClient.post(`/templates/${templateId}/default`, {}, { marketId }); }
