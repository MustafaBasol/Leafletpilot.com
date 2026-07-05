import { apiBaseUrl } from "./config.js";
import { apiClient, ApiError } from "./client.js";

export function listCampaigns(params, marketId) {
  return apiClient.get("/campaigns", { params, marketId });
}

export function getCampaign(campaignId, marketId) {
  return apiClient.get(`/campaigns/${campaignId}`, { marketId });
}

export function getCampaignPreviewHtml(campaignId, marketId) {
  return apiClient.get(`/campaigns/${campaignId}/preview-html`, { marketId });
}

export function createCampaign(payload, marketId) {
  return apiClient.post("/campaigns", payload, { marketId });
}

export function updateCampaign(campaignId, payload, marketId) {
  return apiClient.patch(`/campaigns/${campaignId}`, payload, { marketId });
}

export function cancelCampaign(campaignId, marketId) {
  return apiClient.delete(`/campaigns/${campaignId}`, { marketId });
}

export function parseCampaignText(payload) {
  return apiClient.post("/campaigns/parse-text", payload);
}

export function createCampaignFromText(payload, marketId) {
  return apiClient.post("/campaigns/from-text", payload, { marketId });
}

export function generateCampaignSuggestions(campaignId, payload, marketId) {
  return apiClient.post(`/campaigns/${campaignId}/generate-suggestions`, payload, { marketId });
}

export function generateItemSuggestions(campaignId, itemId, payload, marketId) {
  return apiClient.post(`/campaigns/${campaignId}/items/${itemId}/generate-suggestions`, payload, { marketId });
}

export function resolveCampaignItemMatch(campaignId, itemId, payload, marketId) {
  return apiClient.post(`/campaigns/${campaignId}/items/${itemId}/resolve-match`, payload, { marketId });
}

export function listCampaignFiles(campaignId, marketId) {
  return apiClient.get(`/campaigns/${campaignId}/files`, { marketId });
}

export function createExportJob(campaignId, payload, marketId) {
  return apiClient.post(`/campaigns/${campaignId}/export-jobs`, payload, { marketId });
}

export async function downloadCampaignFile(campaignId, fileId, marketId) {
  const response = await fetch(`${apiBaseUrl}/campaigns/${campaignId}/files/${fileId}/download`, {
    headers: {
      "X-Market-Id": marketId,
    },
  });

  if (!response.ok) {
    throw new ApiError(`Dosya indirilemedi (${response.status} ${response.statusText})`, { status: response.status });
  }

  return response.blob();
}
